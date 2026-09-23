# ADR-0013: Loop real video clips (not still photos) for the demo cameras

**Status**: Accepted

## Context

ADR-0010 replaced `demo-camera`'s synthetic color pattern with a real
still photo per camera, specifically so `apps/inference`'s pretrained
models had genuine content to detect. That worked for the model, but for
a human watching the dashboard during a live demo it doesn't read as a
CCTV feed — a "LIVE" badge over a frame that never moves looks like
exactly what it is, a photograph, undermining the demo's central claim
("this is a platform watching live video"). The user asked directly for
ideas on making the demo look and feel like real, actively-monitored
CCTV, and specifically asked whether real (if not actually public/live)
video could be sourced instead of photos.

## Decision

### 1. Real, short, looping video clips replace stills for four of five cameras

Sourced from [Mixkit](https://mixkit.co) (free stock video, no
attribution required, no login needed to download — see
`infra/demo-camera/media/NOTICE.md` for the exact clip/license per
file). Public CCTV footage itself was considered and rejected: re-
streaming someone else's live public camera raises real legal/ToS
questions this project has no need to take on, and most such feeds are
one-off webcams, not something a demo can depend on staying up.
`Parkiran Truk` keeps its still image (`parkiran.png`) on purpose — it's
the deliberately empty/compliant baseline camera, where "nothing is
moving" is the correct scene, not a shortcoming.

`infra/demo-camera/entrypoint.sh` now branches on file extension:
`-stream_loop -1` for a real video file, `-loop 1` (the image2 demuxer's
own repeat option, since a still frame has no timeline for
`-stream_loop` to loop within) for the one remaining still image. Both
paths explicitly `-map` video from the source and audio from the
existing synthetic sine tone, so this works uniformly whether or not the
source clip carries its own audio track.

### 2. A ticking timestamp overlay, burned into every feed

`drawtext` (via a `ttf-dejavu` font now installed in the image) renders
`CAMERA_LABEL %{localtime\:%d-%m-%Y %H\:%M\:%S}` in the corner of every
stream — a real wall-clock time that visibly advances, not a static
label. This is the single cheapest, most legible "this is actually live"
signal available (the same reason every real DVR/NVR overlay does
exactly this) and needed no new asset sourcing, just an `ffmpeg` filter.

## Consequences

- The four video-backed cameras now show genuine motion — the exact
  people/scenes chosen also happen to make the "compliant" vs.
  "violation" story readable at a glance (an orange/white hardhat on the
  compliant cameras; welding masks with no hardhat on Workshop), which
  the earlier duplicate-photo choice (the same still reused for two
  cameras) didn't.
- `apps/inference`'s detection behavior is unaffected in kind — it still
  samples a frame every `SAMPLE_INTERVAL_SECONDS` and runs the same two
  models — but now against a frame that's actually different call to
  call, which is a more faithful rehearsal of a real deployment than a
  frozen frame was.
- Neither Mixkit license tier's exact legal text was machine-readable at
  authoring time (it loads via a JS modal) — acceptable for this
  internal PoC/demo per the same standing "rotate/verify before real
  production" rule already applied to the pretrained models and the
  earlier photo set, but a real legal read before any external/production
  use is still owed.
- The image now needs a font package (`ttf-dejavu`) it didn't before —
  a small, deliberate addition, not a coincidental dependency.
