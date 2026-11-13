"""Accounts, credentials, sessions and MFA (ADR 0001).

Security properties:
- Responses for register / forgot-password / resend never reveal whether an email exists.
- Unknown accounts still pay the cost of a password verification (timing equalisation).
- Session, verification, reset and invitation tokens are 256-bit random and stored only as hashes.
- Password changes and resets revoke other sessions; resets revoke all of them.
- TOTP codes cannot be replayed; recovery codes are single-use.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pyotp
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from operon.access.context import Actor, AuthContext, RequestMeta
from operon.core.config import Settings
from operon.core.crypto import SecretBox
from operon.core.db import Database
from operon.core.email import EmailMessage, EmailSender
from operon.core.errors import ApiError
from operon.core.rate_limit import Limit, RateLimiter
from operon.core.security import PasswordService, hash_token, new_token
from operon.modules.audit import service as audit
from operon.modules.identity.models import (
    MfaFactor,
    RecoveryCode,
    User,
    UserActionToken,
    UserCredential,
    UserSession,
)
from operon.modules.organisations import service as orgs

LOGIN_PER_IP = Limit("login_ip", 30, 15 * 60)
LOGIN_PER_EMAIL = Limit("login_email", 8, 15 * 60)
MFA_PER_CHALLENGE = Limit("mfa_challenge", 5, 10 * 60)
MFA_PER_USER = Limit("mfa_user", 10, 15 * 60)
EMAIL_ACTIONS_PER_IP = Limit("email_actions_ip", 10, 15 * 60)
EMAIL_ACTIONS_PER_EMAIL = Limit("email_actions_email", 3, 15 * 60)
TOKEN_REDEEM_PER_IP = Limit("token_redeem_ip", 20, 15 * 60)

INVALID_CREDENTIALS = ApiError(401, "invalid_credentials", "The email or password is incorrect.")
RECOVERY_CODE_COUNT = 10
TOTP_ISSUER = "Operon"


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: UserSession


@dataclass(frozen=True)
class MfaChallenge:
    token: str


class IdentityService:
    """Request-scoped: holds the transaction session and shared infrastructure."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        db: Database,
        settings: Settings,
        redis: "Redis",
        passwords: PasswordService,
        secrets_box: SecretBox,
        mailer: EmailSender,
        meta: RequestMeta,
    ) -> None:
        self.s = session
        self.db = db
        self.settings = settings
        self.redis = redis
        self.passwords = passwords
        self.box = secrets_box
        self.mailer = mailer
        self.meta = meta
        self.limiter = RateLimiter(redis)

    # --- helpers ---------------------------------------------------------------------------------

    async def _user_by_email(self, email: str) -> User | None:
        return await self.s.scalar(select(User).where(User.email == email))

    async def _issue_action_token(self, user: User, purpose: str, ttl: timedelta) -> str:
        # Only the newest token of a purpose stays valid.
        await self.s.execute(
            update(UserActionToken)
            .where(
                UserActionToken.user_id == user.id,
                UserActionToken.purpose == purpose,
                UserActionToken.consumed_at.is_(None),
            )
            .values(consumed_at=_now())
        )
        token = new_token()
        now = _now()
        self.s.add(
            UserActionToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=hash_token(token),
                created_at=now,
                expires_at=now + ttl,
            )
        )
        await self.s.flush()
        return token

    async def _redeem_action_token(self, token: str, purpose: str) -> User:
        await self.limiter.hit(TOKEN_REDEEM_PER_IP, self.meta.ip_address or "unknown")
        record = await self.s.scalar(
            select(UserActionToken)
            .where(
                UserActionToken.token_hash == hash_token(token), UserActionToken.purpose == purpose
            )
            .with_for_update()
        )
        if record is None or record.consumed_at is not None or record.expires_at <= _now():
            raise ApiError(
                400, "invalid_token", "This link is invalid or has expired. Request a new one."
            )
        record.consumed_at = _now()
        user = await self.s.get(User, record.user_id)
        if user is None or not user.is_active:
            raise ApiError(
                400, "invalid_token", "This link is invalid or has expired. Request a new one."
            )
        return user

    async def _send_verification(self, user: User) -> None:
        token = await self._issue_action_token(
            user, "verify_email", timedelta(hours=self.settings.verification_token_hours)
        )
        await self.mailer.send(
            EmailMessage(
                to=user.email,
                subject="Confirm your email for Operon",
                text=(
                    f"Hello {user.full_name},\n\nConfirm your email address to finish setting up "
                    f"your Operon account:\n{self.settings.web_base_url}/verify-email?token={token}"
                    f"\n\nThis link expires in {self.settings.verification_token_hours} hours."
                ),
            )
        )

    async def _email_rate_limit(self, email: str) -> None:
        await self.limiter.hit(EMAIL_ACTIONS_PER_IP, self.meta.ip_address or "unknown")
        await self.limiter.hit(EMAIL_ACTIONS_PER_EMAIL, email.lower())

    async def _revoke_sessions(self, user_id: UUID, *, keep: UUID | None = None) -> int:
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        if keep is not None:
            stmt = stmt.where(UserSession.id != keep)
        result = await self.s.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    async def _create_session(self, user: User) -> IssuedSession:
        token = new_token()
        now = _now()
        record = UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=self.settings.session_absolute_hours),
            ip_address=self.meta.ip_address,
            user_agent=(self.meta.user_agent or "")[:400] or None,
        )
        self.s.add(record)
        user.last_login_at = now
        await self.s.flush()
        await audit.record(
            self.s,
            actor=Actor.user(user.id, user.email),
            action="auth.login",
            meta=self.meta,
            target_type="session",
            target_id=record.id,
        )
        return IssuedSession(token, record)

    async def _mfa_factor(self, user_id: UUID, *, confirmed: bool = True) -> MfaFactor | None:
        stmt = select(MfaFactor).where(MfaFactor.user_id == user_id)
        if confirmed:
            stmt = stmt.where(MfaFactor.confirmed_at.is_not(None))
        return await self.s.scalar(stmt)

    def _totp(self, factor: MfaFactor) -> pyotp.TOTP:
        secret = self.box.decrypt(factor.secret_encrypted, context=f"mfa:{factor.user_id}")
        return pyotp.TOTP(secret)

    async def _verify_second_factor(self, user: User, code: str) -> bool:
        """TOTP (no replay) or a single-use recovery code."""
        factor = await self._mfa_factor(user.id)
        if factor is None:
            return False
        code = code.strip().replace(" ", "").replace("-", "")
        if code.isdigit() and len(code) == 6:
            totp = self._totp(factor)
            now = _now()
            for offset in (-1, 0, 1):  # ±30 s clock drift
                at = now + timedelta(seconds=30 * offset)
                step = int(at.timestamp()) // 30
                if totp.verify(code, for_time=at, valid_window=0):
                    if factor.last_used_step is not None and step <= factor.last_used_step:
                        return False
                    factor.last_used_step = step
                    return True
            return False
        recovery = await self.s.scalar(
            select(RecoveryCode)
            .where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == hash_token(code.lower()),
                RecoveryCode.used_at.is_(None),
            )
            .with_for_update()
        )
        if recovery is None:
            return False
        recovery.used_at = _now()
        await audit.record(
            self.s,
            actor=Actor.user(user.id, user.email),
            action="auth.recovery_code_used",
            meta=self.meta,
        )
        return True

    # --- registration and verification -----------------------------------------------------------

    async def register(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        organisation_name: str | None,
        invitation_token: str | None,
    ) -> None:
        """Always succeeds from the caller's point of view (no account enumeration)."""
        await self._email_rate_limit(email)
        existing = await self._user_by_email(email)
        if existing is not None:
            await self.mailer.send(
                EmailMessage(
                    to=existing.email,
                    subject="Someone tried to register with your email",
                    text=(
                        "Someone tried to create an Operon account with this email address. You "
                        "already have an account. If this was you, sign in or reset your password "
                        f"at {self.settings.web_base_url}/forgot-password. Otherwise, ignore this "
                        "email."
                    ),
                )
            )
            return

        invitation = None
        if invitation_token:
            invitation = await orgs.lookup_invitation(self.s, invitation_token)
            if invitation.status != "open" or invitation.invitation.email.lower() != email.lower():
                raise ApiError(
                    400,
                    "invalid_invitation",
                    "This invitation is not valid for this email address.",
                )
        elif not organisation_name:
            raise ApiError(422, "organisation_required", "Enter your organisation's name.")

        now = _now()
        user = User(
            email=email,
            full_name=full_name.strip(),
            is_active=True,
            # The invitation link proves control of the address.
            email_verified_at=now if invitation else None,
        )
        self.s.add(user)
        await self.s.flush()
        self.s.add(
            UserCredential(
                user_id=user.id,
                password_hash=self.passwords.hash(password),
                password_changed_at=now,
            )
        )
        await audit.record(
            self.s,
            actor=Actor.user(user.id, user.email),
            action="auth.register",
            meta=self.meta,
            target_type="user",
            target_id=user.id,
        )
        if invitation_token:
            await orgs.accept_invitation(self.s, token=invitation_token, user=user, meta=self.meta)
        else:
            assert organisation_name is not None
            await orgs.create_organisation(
                self.s, name=organisation_name, owner=user, meta=self.meta
            )
            await self._send_verification(user)

    async def resend_verification(self, email: str) -> None:
        await self._email_rate_limit(email)
        user = await self._user_by_email(email)
        if user is not None and user.is_active and user.email_verified_at is None:
            await self._send_verification(user)

    async def verify_email(self, token: str) -> None:
        user = await self._redeem_action_token(token, "verify_email")
        if user.email_verified_at is None:
            user.email_verified_at = _now()
            await audit.record(
                self.s,
                actor=Actor.user(user.id, user.email),
                action="auth.email_verified",
                meta=self.meta,
                target_type="user",
                target_id=user.id,
            )

    # --- login -----------------------------------------------------------------------------------

    async def login(self, *, email: str, password: str) -> IssuedSession | MfaChallenge:
        await self.limiter.hit(LOGIN_PER_IP, self.meta.ip_address or "unknown")
        await self.limiter.hit(LOGIN_PER_EMAIL, email.lower())

        user = await self._user_by_email(email)
        credential = await self.s.get(UserCredential, user.id) if user else None
        valid = self.passwords.verify(credential.password_hash if credential else None, password)
        if user is None or credential is None or not valid or not user.is_active:
            await audit.record_independent(
                self.db,
                actor=Actor("user", user.id if user else None, email),
                action="auth.login_failed",
                outcome="failure",
                meta=self.meta,
                details={"reason": "invalid_credentials"},
            )
            raise INVALID_CREDENTIALS
        if user.email_verified_at is None:
            raise ApiError(
                403,
                "email_not_verified",
                "Confirm your email address first. Check your inbox, or request a new link.",
                {"resend": True},
            )
        await self.limiter.reset(LOGIN_PER_EMAIL, email.lower())
        if self.passwords.needs_rehash(credential.password_hash):
            credential.password_hash = self.passwords.hash(password)

        if await self._mfa_factor(user.id) is not None:
            challenge = new_token()
            await self.redis.set(
                f"mfa_challenge:{hash_token(challenge)}",
                str(user.id),
                ex=self.settings.mfa_challenge_minutes * 60,
            )
            return MfaChallenge(challenge)
        return await self._create_session(user)

    async def complete_mfa_login(self, *, challenge: str, code: str) -> IssuedSession:
        key = f"mfa_challenge:{hash_token(challenge)}"
        await self.limiter.hit(MFA_PER_CHALLENGE, hash_token(challenge))
        user_id = await self.redis.get(key)
        if not user_id:
            raise ApiError(
                401,
                "mfa_challenge_expired",
                "Your sign-in attempt expired. Enter your email and password again.",
            )
        user = await self.s.get(User, UUID(str(user_id)))
        if user is None or not user.is_active:
            raise ApiError(
                401,
                "mfa_challenge_expired",
                "Your sign-in attempt expired. Enter your email and password again.",
            )
        await self.limiter.hit(MFA_PER_USER, str(user.id))
        if not await self._verify_second_factor(user, code):
            await audit.record_independent(
                self.db,
                actor=Actor.user(user.id, user.email),
                action="auth.mfa_failed",
                outcome="failure",
                meta=self.meta,
            )
            raise ApiError(401, "invalid_code", "That code isn't valid. Try again.")
        await self.redis.delete(key)
        return await self._create_session(user)

    async def authenticate(self, token: str) -> AuthContext | None:
        """Resolve a session cookie. Enforces absolute and idle expiry; slides the idle window."""
        record = await self.s.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        now = _now()
        if record is None or record.revoked_at is not None or record.expires_at <= now:
            return None
        if record.last_seen_at + timedelta(minutes=self.settings.session_idle_minutes) <= now:
            record.revoked_at = now
            return None
        user = await self.s.get(User, record.user_id)
        if user is None or not user.is_active:
            return None
        if now - record.last_seen_at > timedelta(minutes=1):  # limit write amplification
            record.last_seen_at = now
        mfa = await self._mfa_factor(user.id)
        return AuthContext(user.id, user.email, user.full_name, record.id, mfa is not None)

    async def logout(self, auth: AuthContext) -> None:
        record = await self.s.get(UserSession, auth.session_id)
        if record and record.revoked_at is None:
            record.revoked_at = _now()
            await audit.record(
                self.s,
                actor=Actor.user(auth.user_id, auth.email),
                action="auth.logout",
                meta=self.meta,
                target_type="session",
                target_id=record.id,
            )

    # --- passwords -------------------------------------------------------------------------------

    async def request_password_reset(self, email: str) -> None:
        await self._email_rate_limit(email)
        user = await self._user_by_email(email)
        if user is None or not user.is_active:
            return
        token = await self._issue_action_token(
            user, "reset_password", timedelta(minutes=self.settings.password_reset_token_minutes)
        )
        link = f"{self.settings.web_base_url}/reset-password?token={token}"
        minutes = self.settings.password_reset_token_minutes
        await audit.record(
            self.s,
            actor=Actor.user(user.id, user.email),
            action="auth.password_reset_requested",
            meta=self.meta,
        )
        await self.mailer.send(
            EmailMessage(
                to=user.email,
                subject="Reset your Operon password",
                text=(
                    f"Reset your password: {link}\n\n"
                    f"This link expires in {minutes} minutes. "
                    "If you didn't ask for this, ignore this email; your password won't change."
                ),
            )
        )

    async def reset_password(self, *, token: str, new_password: str) -> None:
        user = await self._redeem_action_token(token, "reset_password")
        credential = await self.s.get(UserCredential, user.id)
        if credential is None:
            raise ApiError(400, "invalid_token", "This link is invalid or has expired.")
        credential.password_hash = self.passwords.hash(new_password)
        credential.password_changed_at = _now()
        # Completing a reset proves control of the email address.
        user.email_verified_at = user.email_verified_at or _now()
        revoked = await self._revoke_sessions(user.id)
        await audit.record(
            self.s,
            actor=Actor.user(user.id, user.email),
            action="auth.password_reset",
            meta=self.meta,
            details={"sessions_revoked": revoked},
        )
        await self.mailer.send(
            EmailMessage(
                to=user.email,
                subject="Your Operon password was changed",
                text=(
                    "Your password was just reset and you were signed out everywhere. If this "
                    "wasn't you, reset your password again and contact your administrator."
                ),
            )
        )

    async def change_password(self, auth: AuthContext, *, current: str, new: str) -> None:
        credential = await self.s.get(UserCredential, auth.user_id)
        if credential is None or not self.passwords.verify(credential.password_hash, current):
            await audit.record_independent(
                self.db,
                actor=Actor.user(auth.user_id, auth.email),
                action="auth.password_change_failed",
                outcome="failure",
                meta=self.meta,
            )
            raise ApiError(400, "invalid_password", "Your current password is incorrect.")
        credential.password_hash = self.passwords.hash(new)
        credential.password_changed_at = _now()
        revoked = await self._revoke_sessions(auth.user_id, keep=auth.session_id)
        await audit.record(
            self.s,
            actor=Actor.user(auth.user_id, auth.email),
            action="auth.password_changed",
            meta=self.meta,
            details={"other_sessions_revoked": revoked},
        )

    # --- sessions --------------------------------------------------------------------------------

    async def list_sessions(self, auth: AuthContext) -> list[UserSession]:
        rows = await self.s.scalars(
            select(UserSession)
            .where(
                UserSession.user_id == auth.user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > _now(),
            )
            .order_by(UserSession.last_seen_at.desc())
        )
        return list(rows.all())

    async def revoke_session(self, auth: AuthContext, session_id: UUID) -> None:
        record = await self.s.scalar(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == auth.user_id,
                UserSession.revoked_at.is_(None),
            )
        )
        if record is None:
            raise ApiError(404, "not_found", "The requested resource was not found.")
        record.revoked_at = _now()
        await audit.record(
            self.s,
            actor=Actor.user(auth.user_id, auth.email),
            action="auth.session_revoked",
            meta=self.meta,
            target_type="session",
            target_id=session_id,
        )

    # --- MFA -------------------------------------------------------------------------------------

    async def start_totp_setup(self, auth: AuthContext) -> tuple[str, str]:
        if await self._mfa_factor(auth.user_id) is not None:
            raise ApiError(
                409,
                "mfa_already_enabled",
                "Two-factor authentication is already on. Turn it off first to "
                "replace your authenticator.",
            )
        secret = pyotp.random_base32()
        pending = await self._mfa_factor(auth.user_id, confirmed=False)
        encrypted = self.box.encrypt(secret, context=f"mfa:{auth.user_id}")
        if pending is None:
            self.s.add(
                MfaFactor(user_id=auth.user_id, secret_encrypted=encrypted, created_at=_now())
            )
        else:
            pending.secret_encrypted = encrypted
            pending.created_at = _now()
            pending.last_used_step = None
        await self.s.flush()
        uri = pyotp.TOTP(secret).provisioning_uri(name=auth.email, issuer_name=TOTP_ISSUER)
        return secret, uri

    async def confirm_totp(self, auth: AuthContext, code: str) -> list[str]:
        await self.limiter.hit(MFA_PER_USER, str(auth.user_id))
        factor = await self._mfa_factor(auth.user_id, confirmed=False)
        if factor is None or factor.confirmed_at is not None:
            raise ApiError(409, "mfa_setup_not_started", "Start two-factor setup first.")
        code = code.strip().replace(" ", "")
        if not self._totp(factor).verify(code, valid_window=1):
            raise ApiError(
                400,
                "invalid_code",
                "That code isn't valid. Check your authenticator app's time and try again.",
            )
        factor.confirmed_at = _now()
        factor.last_used_step = int(_now().timestamp()) // 30
        codes = await self._replace_recovery_codes(auth.user_id)
        await audit.record(
            self.s,
            actor=Actor.user(auth.user_id, auth.email),
            action="auth.mfa_enabled",
            meta=self.meta,
        )
        await self.mailer.send(
            EmailMessage(
                to=auth.email,
                subject="Two-factor authentication is on",
                text="Two-factor authentication was turned on for your Operon account.",
            )
        )
        return codes

    async def _replace_recovery_codes(self, user_id: UUID) -> list[str]:
        await self.s.execute(
            update(RecoveryCode)
            .where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
            .values(used_at=_now())
        )
        codes = [
            f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(RECOVERY_CODE_COUNT)
        ]
        for code in codes:
            self.s.add(RecoveryCode(user_id=user_id, code_hash=hash_token(code.replace("-", ""))))
        await self.s.flush()
        return codes

    async def disable_totp(self, auth: AuthContext, *, password: str, code: str) -> None:
        credential = await self.s.get(UserCredential, auth.user_id)
        user = await self.s.get(User, auth.user_id)
        if (
            credential is None
            or user is None
            or not self.passwords.verify(credential.password_hash, password)
        ):
            raise ApiError(400, "invalid_password", "Your password is incorrect.")
        await self.limiter.hit(MFA_PER_USER, str(auth.user_id))
        if not await self._verify_second_factor(user, code):
            raise ApiError(400, "invalid_code", "That code isn't valid.")
        factor = await self._mfa_factor(auth.user_id)
        if factor:
            await self.s.delete(factor)
        await self.s.execute(
            update(RecoveryCode)
            .where(RecoveryCode.user_id == auth.user_id, RecoveryCode.used_at.is_(None))
            .values(used_at=_now())
        )
        await audit.record(
            self.s,
            actor=Actor.user(auth.user_id, auth.email),
            action="auth.mfa_disabled",
            meta=self.meta,
        )
        await self.mailer.send(
            EmailMessage(
                to=auth.email,
                subject="Two-factor authentication was turned off",
                text=(
                    "Two-factor authentication was turned off for your Operon account. If this "
                    "wasn't you, change your password now."
                ),
            )
        )

    async def regenerate_recovery_codes(self, auth: AuthContext, code: str) -> list[str]:
        user = await self.s.get(User, auth.user_id)
        await self.limiter.hit(MFA_PER_USER, str(auth.user_id))
        if user is None or not await self._verify_second_factor(user, code):
            raise ApiError(400, "invalid_code", "That code isn't valid.")
        codes = await self._replace_recovery_codes(auth.user_id)
        await audit.record(
            self.s,
            actor=Actor.user(auth.user_id, auth.email),
            action="auth.recovery_codes_regenerated",
            meta=self.meta,
        )
        return codes

    # --- profile ---------------------------------------------------------------------------------

    async def get_user(self, user_id: UUID) -> User:
        user = await self.s.get(User, user_id)
        if user is None:
            raise ApiError(401, "unauthenticated", "Sign in to continue.")
        return user

    async def update_profile(self, auth: AuthContext, *, full_name: str) -> User:
        user = await self.get_user(auth.user_id)
        if full_name.strip() != user.full_name:
            await audit.record(
                self.s,
                actor=Actor.user(auth.user_id, auth.email),
                action="user.profile_updated",
                meta=self.meta,
                details={"full_name": {"from": user.full_name, "to": full_name.strip()}},
            )
            user.full_name = full_name.strip()
        return user
