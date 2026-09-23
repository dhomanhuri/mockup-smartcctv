# Demo media provenance

There is no real CCTV feed on the lab host, so each "camera" is a
`demo-camera` container looping one real, licensed clip into MediaMTX
over RTSP (see `../entrypoint.sh`) — genuine video with genuine motion
for four of the five, not a still photo standing in for a live feed (see
ADR-0013; a still photo was the original v1 approach — ADR-0010/0011 —
kept only for `parkiran.png`, a deliberately empty/compliant baseline).
None of these depict a real Pertamina EP site or a real incident.

| File | Used as | Source | License |
|---|---|---|---|
| `gerbang.mp4` | Gerbang Utama, APD compliant (orange hardhat) | [Worker walking in industrial machine corridor](https://mixkit.co/free-stock-video/worker-walking-in-industrial-machine-corridor-23378/), Mixkit | Mixkit Stock Video license (free, no attribution required) |
| `produksi.mp4` | Area Produksi 1, APD compliant (white hardhat) | [An engineer working through the warehouse](https://mixkit.co/free-stock-video/an-engineer-working-through-the-warehouse-23010/), Mixkit | Mixkit Stock Video license |
| `workshop.mp4` | Workshop, APD violation (welding masks/cap, no hardhat) | [Workers welding heavy metal in a factory](https://mixkit.co/free-stock-video/workers-welding-heavy-metal-in-a-factory-47755/), Mixkit | Mixkit Stock Video license |
| `jalur.mp4` | Jalur Kendaraan, vehicle person-in-zone (people + forklift) | [Business people walking through the warehouse](https://mixkit.co/free-stock-video/business-people-walking-through-the-warehouse-23550/), Mixkit | Mixkit Stock Video license |
| `parkiran.png` | Parkiran Truk, empty baseline (no violation) — still image, unchanged from ADR-0010 | [Green pickup truck.png](https://commons.wikimedia.org/wiki/File:Green_pickup_truck.png), Wikimedia Commons | CC BY-SA 3.0 |

Mixkit's clips are tagged either "Stock Video Free License" or "Stock
Video Restricted License" depending on the clip; both permit personal
and commercial use with no attribution, per Mixkit's own license page
(https://mixkit.co/license/ — the exact legal text loads via JS and
wasn't fully machine-readable when this was written). Fine for this
internal PoC/demo; **re-verify the exact terms before any real
production use**, per the standing rule in `docs/runbook/credentials.md`
to rotate/verify everything here before going live — same caveat already
applied to `apps/inference/models/NOTICE.md`.

`jalur.mp4` does not depict anyone actually riding in a truck bed — free
stock footage of that specific, staged-looking violation doesn't seem to
exist, unsurprisingly. It's used purely because it reliably contains
real, moving, detectable people. The vehicle-violation rule is a zone
heuristic (see `apps/inference/inference.py`'s module docstring and
ADR-0010): any person detected inside that camera's configured "cargo
bed" zone counts as a violation, regardless of what the footage actually
shows. Swap in a real calibration feed once real cameras are installed.
