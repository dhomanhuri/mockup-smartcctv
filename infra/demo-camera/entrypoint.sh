#!/bin/sh
set -e

MEDIAMTX_HOST=${MEDIAMTX_HOST:-mediamtx}
STREAM_PATH=${STREAM_PATH:-demo-gerbang}
MEDIA_FILE=${MEDIA_FILE:-/media/gerbang.mp4}

echo "waiting for mediamtx at ${MEDIAMTX_HOST}:8554 ..."
until nc -z "$MEDIAMTX_HOST" 8554; do
  sleep 2
done
echo "mediamtx is up, publishing ${MEDIA_FILE} as a looping feed to ${STREAM_PATH}"

# A real (short, CC-licensed) video clip loops with -stream_loop on the
# input; a still image needs -loop 1 instead (a stream_loop on a single
# still frame just plays it once and stops, since there's no timeline to
# loop back inside — the image2 demuxer's own -loop option is the one
# that repeats a still indefinitely). Only Parkiran Truk is still a still
# image (a deliberately empty/compliant baseline, see media/NOTICE.md);
# everything else here is real video with real motion now, not a photo
# standing in for one — see ADR-0013.
case "$MEDIA_FILE" in
  *.mp4|*.webm|*.mov|*.mkv)
    LOOP_FLAG="-stream_loop -1"
    ;;
  *)
    LOOP_FLAG="-loop 1"
    ;;
esac

# -map picks video from input 0 and audio from input 1 explicitly,
# regardless of whether the source clip already has its own audio track —
# keeps this working the same way for both a muxed real video and a bare
# still image without two different ffmpeg invocations.
#
# The drawtext overlay is a real, ticking wall-clock timestamp (not a
# static "LIVE" label baked into the source) burned into the corner —
# the single cheapest, most recognizable signal that a feed is actually
# live rather than a loop, the same way a real DVR/NVR overlay reads.
# CAMERA_LABEL defaults to the stream path so each tile is still
# distinguishable without needing a different drawtext per camera.
# %{localtime} is left with no explicit strftime format on purpose —
# every colon inside a custom format (e.g. %H:%M:%S) is ALSO read as an
# argument separator by drawtext's own %{...} expansion parser, one level
# below the filtergraph's :-as-option-separator escaping, and stacking
# escapes for both at once broke ("%{localtime} requires at most 1
# arguments") until this was simplified to ffmpeg's built-in default
# format ("%Y-%m-%d %H:%M:%S") instead of trying to fight the escaping.
CAMERA_LABEL=${CAMERA_LABEL:-$STREAM_PATH}

# 960x540 + preset ultrafast (down from 1280x720 + veryfast): 5 of these
# run concurrently on the same host as apps/inference's own CPU-bound
# YOLO inference, and on a 4-core lab VM that combination fell far enough
# behind real time (observed: only ~90s of output produced per ~30
# minutes of wall-clock) that RTSP consumers (MediaMTX's HLS muxer,
# inference's cv2.VideoCapture) saw no fresh frame at all — "no frame
# available yet" logged forever, not a streaming or code bug. This is a
# CPU-budget tradeoff, not a quality target: still clearly legible in a
# camera tile, just cheaper to encode ×5 at once. See ADR-0013 and the
# runbook's troubleshooting entry for this exact symptom.
exec ffmpeg -re $LOOP_FLAG \
  -i "$MEDIA_FILE" \
  -f lavfi -i "sine=frequency=220:sample_rate=44100" \
  -map 0:v:0 -map 1:a:0 \
  -vf "scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2:color=0x11151a,drawtext=fontfile=/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf:text='${CAMERA_LABEL} %{localtime}':x=12:y=h-th-12:fontsize=16:fontcolor=white:borderw=2:bordercolor=black@0.7:box=1:boxcolor=black@0.35:boxborderw=5" \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p -g 30 \
  -c:a aac -b:a 64k \
  -f rtsp -rtsp_transport tcp "rtsp://${MEDIAMTX_HOST}:8554/${STREAM_PATH}"
