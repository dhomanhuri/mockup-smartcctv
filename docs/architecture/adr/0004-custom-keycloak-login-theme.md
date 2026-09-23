# ADR-0004: Override Keycloak's `template.ftl`, not just its CSS

**Status**: Accepted

## Context

The brand ask was a split-screen login page (dark hero panel with
headline on one side, the actual form on the other) matching a reference
design, adapted with Pertamina EP branding. Keycloak's default login
themes (both the legacy `keycloak` theme and the newer `keycloak.v2`) render
everything inside a single centered card — there's no built-in variant
that produces a two-column layout.

A first attempt tried to get there with CSS alone, layered on the
inherited `keycloak` theme. It silently failed: the selectors were
guessed (`.kc-logo-text`, `body.login-pf`, `.btn-primary`) rather than
taken from the real rendered markup, and none of them actually matched —
the login page kept its default look with none of the intended styling
applied, without any error to signal that.

## Decision

Extract the actual base theme templates from the Keycloak image
(`org.keycloak.keycloak-themes-<version>.jar`, under `theme/base/login/`)
to get the real macro contract and class names, then override
`login/template.ftl` in the custom `pertaminaep` theme with a version
that wraps the **same nested sections** (`header`, `form`,
`socialProviders`, `info`, etc.) in a `.vg-split` / `.vg-hero` / `.vg-panel`
two-column layout instead of the default single card. Because every
other auth page (`login.ftl`, `login-password.ftl`, forgot-password,
OTP, ...) imports this same `template.ftl` and calls the same
`registrationLayout` macro, one file override covers all of them.

CSS selectors were then written to match the **real** class names
(`pf-c-form-control`, `pf-c-button.pf-m-primary`, `#kc-header-wrapper`,
`html.login-pf`), confirmed by inspecting the actual rendered HTML rather
than assumed from a generic PatternFly reference.

## Consequences

- One `template.ftl` + one `login.css` covers login, forgot-password, and
  every other flow page — no per-page duplication.
- Overriding a Freemarker macro is riskier than overriding CSS (a syntax
  error breaks every auth page, not just cosmetics) — every change here
  should be verified by fetching the rendered page and checking Keycloak's
  logs for FreeMarker exceptions before considering it done.
- This repo has no way to render a real screenshot in its current sandbox
  (no headless-browser system deps, no root to install them) — changes in
  this theme are verified structurally (HTML/CSS output, HTTP status),
  not visually. See [troubleshooting.md](../../runbook/troubleshooting.md).
- How the actual Pertamina EP logo asset is placed on this theme's dark
  panel (vs. the dashboard's light header) is its own decision — see
  [ADR-0009](0009-brand-palette-from-logo.md).
