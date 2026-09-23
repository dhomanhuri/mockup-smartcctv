# ADR-0001: One Keycloak realm, roles instead of separate admin realm

**Status**: Accepted

## Context

The platform needs two kinds of human users: operators who watch cameras
and violations, and platform admins who manage user accounts. The first
draft put admins in a **separate realm** (`visionguard-admin`) with its
own client and login page, on the theory that admin access deserved
stronger isolation.

## Decision

Use **one realm** (`visionguard`) for everyone, with two realm roles
(`operator`, `admin`). Both log in through the same client
(`visionguard-dashboard`) and the same PKCE flow. `/admin.html` is a
separate frontend page but authenticates against the same realm/session —
it just checks for the `admin` role in the token before rendering
anything, and shows "access denied" otherwise.

## Consequences

- Simpler mental model and simpler realm-import JSON — one set of
  clients/roles/users, not two parallel ones.
- One SSO session covers both the operator dashboard and the admin
  dashboard — no separate login when an admin wants to switch between
  them.
- Privileged Keycloak Admin REST API calls still don't trust the token's
  `admin` role directly for authorization against Keycloak itself — see
  [ADR-0006](0006-service-account-for-admin-api.md) for why a dedicated
  service-account client does that part.
- If a future requirement genuinely needs admins to be a fully separate
  security domain (e.g. a different identity source, different session
  lifetime), that would justify revisiting this and splitting the realm.
