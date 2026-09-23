# Business Requirements Document — Smart CCTV AI

Status: written for the demo/POC stage · Owner: HSE & Security Operations, Pertamina EP

## 1. Business problem

Pertamina EP operates CCTV across production areas, gates, loading docks,
and vehicle parking, but footage today is reviewed manually or only
after an incident is already reported. Two categories of preventable
incident recur often enough to justify automated detection:

- **Safety non-compliance** — personnel entering work areas without
  required PPE (starting with helmets).
- **Vehicle violations** — unsafe practices around site vehicles, most
  visibly personnel riding in a truck bed.

Manual monitoring doesn't scale across many cameras and many hours, and
by the time footage is reviewed after an incident, the preventive value
is gone.

## 2. Business objectives

1. Detect the two violation classes above **in near real time**, not
   after the fact.
2. Get an alert to the right people (HSE/Ops) within seconds of
   detection, not at end-of-shift review.
3. Keep an auditable record of every detected violation (who/what/where/
   when/confidence) for compliance reporting and trend analysis.
4. Onboard a new camera into monitoring **by IP address**, with no
   on-site installation work beyond the camera itself.
5. Keep the whole platform on-premise — footage and detection data stay
   inside Pertamina EP's own network, no cloud dependency for the
   critical detection→alert path.

## 3. Stakeholders

| Stakeholder | Interest |
|---|---|
| HSE / Safety Operations | Primary consumer of alerts; defines what counts as a violation |
| Site Operators | Day-to-day dashboard users — watch cameras, acknowledge alerts |
| Platform Admin | Manages who has dashboard access |
| IT / Infrastructure | Owns the on-prem server(s) the platform runs on |
| Pertamina EP corporate identity | Brand presentation (login page, dashboard branding) |

## 4. Scope

**In scope for the platform** (this repository): camera onboarding by
IP, live viewing, violation event ingestion/storage/review, case
management (assign, status, notes), email alerting, authentication with
3-tier role separation (Operator / Supervisor / Admin — see
[ADR-0011](../docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md)),
on-premise single-server deployment.

**Explicitly out of scope for the platform**: training a custom
computer-vision model. The platform is built to receive detections from
*any* inference worker through one stable API contract — it now runs
real (pretrained, not trained-in-house) inference by default; see
[ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md)
and, for the original simulated milestone this replaced,
[ADR-0003](../docs/architecture/adr/0003-simulated-inference.md).

## 5. Success metrics (target, once a real model is integrated)

- Time from violation occurring on camera to alert reaching HSE:
  target under 30 seconds.
- False-positive rate low enough that operators don't start ignoring
  alerts (specific threshold to be set once real model precision is
  known).
- 100% of onboarded cameras report status (online/no-signal) accurately
  in the dashboard at all times.
- Zero violation records lost between detection and the operator's
  screen (durability, not just speed).

## 6. Constraints & assumptions

- Deployment is on-premise on hardware Pertamina EP provides; no
  assumption of GPU availability is made by the platform itself (the
  current demo has none — see [HLD.md](../docs/architecture/HLD.md)).
- Cameras are assumed to expose a standard RTSP stream (or ONVIF
  discovery of one) — the platform does not target proprietary
  camera-vendor SDKs.
- Corporate SMTP relay details are not yet available; the demo uses a
  local catcher (Mailpit) as a stand-in with an identical integration
  contract.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Real model precision unknown until trained | Platform's event contract is model-agnostic; swapping the simulator for a real worker requires no platform changes |
| On-prem hardware may lack GPU capacity for many camera streams | Non-functional notes in [HLD.md](../docs/architecture/HLD.md) flag this as a scale question to revisit |
| Exact official brand guideline (PMS/hex values) not yet provided | Palette was read directly off the real logo file rather than a guideline doc — see [ADR-0009](../docs/architecture/adr/0009-brand-palette-from-logo.md); close enough for the demo, worth confirming against the official guideline later |
