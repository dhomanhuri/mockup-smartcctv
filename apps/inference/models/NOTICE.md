# Model provenance

Both files here are pretrained third-party weights, used unmodified —
no training was done as part of this project (training remains explicitly
out of scope; see `docs/architecture/adr/0003-simulated-inference.md` and
`0010-real-pretrained-inference.md`).

## `hardhat.pt`

- Source: [keremberke/yolov8n-hard-hat-detection](https://huggingface.co/keremberke/yolov8n-hard-hat-detection) on Hugging Face
- Architecture: YOLOv8-nano, fine-tuned on the public "Hard Hat Workers" dataset
- Classes: `Hardhat`, `NO-Hardhat`
- Reported mAP@0.5: 0.836 (per the model card)
- License: not explicitly stated on the model card at the time of download
  (2026-09-08). Acceptable for this internal PoC/demo; **re-verify the
  license (and the upstream "Hard Hat Workers" dataset's terms) before any
  real production use**, per the standing rule in
  `docs/runbook/credentials.md` to rotate/verify everything here before
  going live.

## `yolov8n.pt`

- Source: [Ultralytics YOLOv8 official release assets](https://github.com/ultralytics/assets/releases) (v8.3.0), COCO-pretrained, unmodified
- Used only for its stock `person` class (class id 0) — see
  `apps/inference/inference.py` for how that's turned into a vehicle-zone
  heuristic
- License: AGPL-3.0 (Ultralytics' default license for the `ultralytics`
  package and its released weights) — fine for this internal PoC; flag to
  legal/procurement before external distribution or production use, since
  AGPL carries source-disclosure obligations for networked use.
