"""A fake OpenID Connect provider with a real RSA signing key (protocol-level test server)."""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://idp.test"
CLIENT_ID = "operon-client"
CLIENT_SECRET = "idp-client-secret-0123456789"


@dataclass
class FakeIdP:
    key: Any = field(
        default_factory=lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    kid: str = "key-1"
    codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    token_requests: list[dict[str, str]] = field(default_factory=list)

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}]}

    def sign(self, claims: dict[str, Any], *, key: Any = None, kid: str | None = None) -> str:
        return jwt.encode(
            claims, key or self.key, algorithm="RS256", headers={"kid": kid or self.kid}
        )

    def authorize(self, authorize_url: str, **claims: Any) -> str:
        """Simulate the user signing in at the provider; returns the authorization code."""
        q = {k: v[0] for k, v in parse_qs(authorize_url.split("?", 1)[1]).items()}
        now = int(time.time())
        base = {
            "iss": ISSUER,
            "aud": q["client_id"],
            "sub": "user-123",
            "email": "pat@acme.example",
            "email_verified": True,
            "name": "Pat Example",
            "nonce": q["nonce"],
            "iat": now,
            "exp": now + 300,
        }
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "claims": {**base, **claims},
            "challenge": q["code_challenge"],
            "query": q,
        }
        return code

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                },
            )
        if path == "/jwks":
            return httpx.Response(200, json=self.jwks())
        if path == "/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.token_requests.append(form)
            auth = base64.b64decode(request.headers["authorization"].split()[1]).decode()
            if auth != f"{CLIENT_ID}:{CLIENT_SECRET}":
                return httpx.Response(401, json={"error": "invalid_client"})
            issued = self.codes.pop(form.get("code", ""), None)
            if issued is None:
                return httpx.Response(400, json={"error": "invalid_grant"})
            verifier = form["code_verifier"].encode()
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b"=").decode()
            )
            if challenge != issued["challenge"]:
                return httpx.Response(400, json={"error": "invalid_grant", "detail": "pkce"})
            token = issued.get("token") or self.sign(issued["claims"])
            return httpx.Response(
                200, json={"id_token": token, "access_token": "x", "token_type": "Bearer"}
            )
        return httpx.Response(404)
