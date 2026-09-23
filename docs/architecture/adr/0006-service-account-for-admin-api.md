# ADR-0006: Service-account client for the Admin Dashboard's user management

**Status**: Accepted

## Context

The Admin Dashboard (`/admin.html`) lets a platform admin create and
manage Smart CCTV AI users without touching Keycloak's own console. That
requires calling Keycloak's Admin REST API (`/admin/realms/visionguard/users/...`).
The naive approach — grant the admin's own browser-issued token
`realm-management` client roles so it can call the Admin API directly —
would mean a token that lives in the browser (sessionStorage, subject to
XSS/exfiltration risk) also carries the power to create and modify users.

## Decision

Create a **separate confidential client**, `visionguard-user-manager`
(`serviceAccountsEnabled: true`, has a client secret, `publicClient:
false`), scoped with exactly the `realm-management` roles needed
(`manage-users`, `view-users`, `query-users`, `view-realm`). The backend
obtains its own access token for this client via the `client_credentials`
grant and uses **that** token for every Keycloak Admin API call.

The human admin's own browser token never touches the Admin API. It only
needs to prove — via the `admin` realm role, checked by
`get_current_admin` — that the human is allowed to trigger the backend
into acting on their behalf.

## Consequences

- Compromising a browser session (token theft, XSS) does not directly
  grant Keycloak admin power — the service-account credential never
  leaves the server.
- Getting this working required setting `fullScopeAllowed: true` on the
  service-account client — without it, the issued token silently omitted
  the assigned `realm-management` roles from its claims, and every Admin
  API call returned 403 despite the role assignment looking correct.
  See [troubleshooting.md](../../runbook/troubleshooting.md).
- The service-account client's secret
  (`KC_USER_MANAGER_CLIENT_ID`/`KC_USER_MANAGER_SECRET` in `.env`) is
  itself a credential worth rotating before any real deployment, same as
  everything else in [credentials.md](../../runbook/credentials.md).
