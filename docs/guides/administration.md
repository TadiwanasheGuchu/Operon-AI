# Administration guide

For owners and administrators. Everything here is under **Administration** in the sidebar, and
every change is recorded in the **Audit log**.

## Members and roles

- **Members → Invite.** Invitations expire after 7 days. You can assign roles up to your own.
- **Built-in roles:**
  - *Owner:* everything, including deleting the organisation.
  - *Administrator:* everything except ownership.
  - *Operations manager*, *Approver*, *Analyst*, *Viewer.*
- **Roles** lists each role's permissions. Custom roles aren't available yet.
- Removing a member signs them out of this organisation at once. Requests they own keep their
  history.

## Security policy

- **Require two-factor authentication** (**Organisation → Security policy**). Members without it
  can't open the organisation until they set it up. Turn it on for yourself first.
- Sessions expire after 60 idle minutes and 12 hours in total.

## Single sign-on

Operon supports any OpenID Connect provider: Microsoft Entra ID, Okta, Google Workspace,
Keycloak and others. Configure it in **Organisation → Single sign-on**.

1. **Register Operon with your provider** as a web application:
   - redirect URI: copy it from the panel (`https://<your Operon address>/api/v1/auth/sso/callback`);
   - grant type: authorisation code;
   - scopes: `openid email profile`.

   Your provider then gives you a client ID and a client secret.
2. **Enter the issuer URL, client ID and secret**, then save. The issuer is, for example:
   - Entra: `https://login.microsoftonline.com/<tenant id>/v2.0`;
   - Okta: `https://<org>.okta.com`;
   - Google: `https://accounts.google.com`.

   The secret is encrypted and never shown again; leave the field blank to keep it.
3. **Add your email domains.** For each one, publish the TXT record shown (name
   `_operon-verification.<domain>`), then choose **Verify**. DNS can take a while to update. A
   domain can belong to only one Operon organisation, and public email domains (gmail.com and
   similar) aren't accepted.
4. **Choose who can join.**
   - *Create accounts on first sign-in* on: anyone at a verified domain who signs in becomes a
     member with the default role. Owner and administrator can't be granted this way.
   - Off: only invited members can sign in with SSO.
5. **Turn on single sign-on.** Saving checks that your provider responds. People then choose
   **Sign in with SSO** on the sign-in page and enter their work email.
6. **Optional: require single sign-on.** Members at verified domains can no longer use a
   password. Owners keep password sign-in as a break-glass in case your provider is down. Keep
   that account protected with two-factor authentication.

Operon only accepts sign-ins where the provider confirms the email address (`email_verified`).
If sign-in fails, the sign-in page says why. The audit log shows `sso.configured`,
`sso.domain_verified` and `member.joined` (via SSO).

## Data retention

**Organisation → Data retention** sets how long logs are kept:

| Record | Default | Allowed |
|---|---|---|
| Audit log | 730 days | 365–3650 |
| Assistant conversations | 90 days | 7–3650 |
| Assistant and agent run logs | 180 days | 30–3650 |
| Integration sync history | 90 days | 7–3650 |

Older records are deleted automatically, every few minutes. Each purge is audited as
`retention.applied`. Insights, incidents, purchase requests and their histories are business
records and are never deleted by retention.

## Exporting your data

**Organisation → Export data → Download export** produces a ZIP with:

- one JSON Lines file per kind of record (members, operational data, insights, incidents,
  workflows, agent runs, the audit log, …);
- a `manifest.json` listing the counts and what isn't included.

Not included:

- integration credentials;
- passwords and two-factor secrets;
- invitation tokens;
- the SSO client secret;
- members' private assistant conversations.

Up to five exports a day; each one is audited.

## Integrations, AI and agents

- **Integrations:** see the [onboarding guide](onboarding.md). Credentials are write-only. Pause,
  resume, change the interval, or disconnect from the connection page.
- **AI** (**Intelligence → Settings**): off by default. Choose the provider and set a monthly
  token budget. The assistant and agents stop when the budget is used.
- **Agents** (**AI agents**): the inventory replenishment agent acts for a member you choose and
  can never do more than that member. Its only write is to draft purchase requests, and those
  still need approval. Every run's full log is kept for the retention period.
