# ADR-0009: Derive the whole UI palette from the real Pertamina EP logo

**Status**: Accepted

## Context

Earlier styling (both the dashboard and the Keycloak login theme) used
hand-picked colors loosely inspired by "corporate red" without a real
brand asset to check against, and a hand-drawn SVG recreation of the
Pertamina EP mark. The user then supplied the actual logo file
(`assets/brand/pertamina-ep-logo.jpg`) and asked for the palette —
Keycloak theme through to the dashboard — to be built from its real
colors, and for the asset itself to be used directly rather than
redrawn.

The source file is a JPEG with a plain white background and a dark
wordmark ("PERTAMINA" in dark gray, "EP" in a white-on-red pill) — fine
on a light surface, but illegible if dropped directly onto the dark
Keycloak login panel. No image-editing tooling (Pillow, ImageMagick) was
available in this environment to cleanly key out the white background
(no root access to install system packages) — see
[troubleshooting.md](../../runbook/troubleshooting.md) if that's still
true when this is revisited.

## Decision

**Colors** — three tokens read directly off the logo, used as the base
for every other color decision in both `apps/frontend/styles.css` and
the Keycloak theme:

| Token | Hex | Role |
|---|---|---|
| Brand red | `#E4032E` | Primary accent — buttons, links, focus rings, header/login accent stripe |
| Brand blue | `#0067B1` | Secondary accent — admin badge, secondary links, informational elements |
| Brand green | `#8DC63F` | Doubles as the brand color and the conventional "success" semantic (deliberate — see below) |

Warning stays amber (`#C4841F`) — the one severity color not already
claimed by a brand hue, so it still reads as visually distinct.
"Critical" severity uses a deeper red (`#A3001A`) than the brand accent,
so a critical badge doesn't read as merely "another red button."

Using the same hue for both the *brand* and the *success* semantic is a
deliberate exception to the usual rule of keeping decorative accent and
semantic color separate — it isn't a coincidence to correct, it's what
the actual logo gives us, and green-as-brand and green-as-success point
the same direction here.

**Logo asset** — the real JPEG is used as-is (`apps/frontend/` and
`infra/keycloak/themes/pertaminaep/login/resources/img/`, both copies of
`assets/brand/pertamina-ep-logo.jpg`), not redrawn:

- On light surfaces (dashboard header), it's dropped in directly — its
  white background matches the surface.
- On the dark Keycloak login panel, it sits inside a small white rounded
  card (`.vg-logo-card`) instead of floating directly on dark chrome —
  an honest, common pattern for placing a light-background logo asset on
  dark chrome, rather than a mismatch to explain away.

## Consequences

- One canonical logo file (`assets/brand/`) with two consuming copies,
  documented as copies rather than independently-drawn assets — keep
  them in sync if the source logo ever changes.
- If proper image-editing tooling becomes available later, the white
  background could be keyed to transparent and the wordmark recolored
  per-theme instead of using the white-card workaround — worth
  revisiting, not urgent (the current result is legitimate, not a
  placeholder).
- The extracted hex values are a visual read of the JPEG, not sourced
  from an official Pertamina brand guideline PDF/PMS spec — close
  enough for this demo, but worth confirming against the real guideline
  before this ships anywhere more official.
