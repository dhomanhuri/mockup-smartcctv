# ADR-0008: Rename the product to "Smart CCTV AI"; keep `visionguard` as the internal slug

**Status**: Accepted

## Context

The project was built and named "VisionGuard CCTV" throughout — repo
folder, Keycloak realm, client IDs, database names, Python logger
namespaces, as well as every user-facing title, header, and email. The
product was then renamed to **Smart CCTV AI**.

A literal find-and-replace of every occurrence would touch the Keycloak
realm name (which is embedded in every OIDC URL:
`/auth/realms/visionguard/...`), client IDs referenced throughout
`apps/frontend/auth.js` and `apps/backend`, the Postgres database name,
the docker-compose project name (derived from the folder name), and the
repo folder path itself — none of which any user ever actually reads
during normal use, but all of which are load-bearing plumbing that a
typo in this rename could silently break (this project has already hit
several silent-failure bugs from smaller mismatches — see
[troubleshooting.md](../../runbook/troubleshooting.md)).

## Decision

Split the rename into two categories:

1. **User-facing display strings** — renamed to "Smart CCTV AI": page
   titles, dashboard header, login page hero/title, email subject lines
   and From display name, documentation prose describing the product.
2. **Internal technical identifiers** — left as `visionguard` /
   `vg-*`: the repo folder name, the Keycloak realm name and its client
   IDs (`visionguard-dashboard`, `visionguard-user-manager`), the
   Postgres database/user names, Python logger namespaces
   (`visionguard.notifications`, etc.), and `sessionStorage` keys in the
   frontend (`vg_tokens`).

The two demo user passwords (`SmartCctvAdmin#2026`,
`SmartCctvOperator#2026`) were updated even though they're technically
just secrets, since a password containing the *old* product name as a
mnemonic would be a confusing, avoidable inconsistency for anyone using
[credentials.md](../../runbook/credentials.md) going forward. Database
passwords (`VisionGuardDb#2026`, etc.) were left alone — nobody types
those from memory, and they carry no branding association a person
would notice.

## Consequences

- No Keycloak realm reset was strictly *required* by this rename (only
  the smaller `smtpServer`/`fullScopeAllowed` config bits from earlier
  needed that) — but since several display fields (`displayNameHtml`,
  client `name`, user `lastName`, passwords) changed at once, a clean
  re-import was simpler and safer than hand-crafting a dozen individual
  `kcadm.sh update` commands. See
  [deployment.md](../../runbook/deployment.md) for the reset procedure.
- A reader who greps the codebase for "Smart CCTV AI" and finds
  `visionguard` everywhere underneath should not read that as an
  incomplete rename — it's the documented split above. This ADR is the
  place that explains it once instead of scattering "yes this is
  intentional" comments through the code.
- If the product is renamed again in the future, the same split
  applies: update the display strings, leave the internal slug alone
  unless there's a concrete reason (e.g. a second, unrelated product
  needing to coexist in the same Keycloak instance) to justify the risk
  of touching load-bearing identifiers.
