#!/usr/bin/env bash
# Reel rendern: HTML -> 960 Frames -> H.264 MP4 (1080x1920, 30 fps, 32 s)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
FF="$(python3 -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
NAME="${1:-reel_01_gamma}"

node "$HERE/tools/render.js" "$HERE/$NAME.html"
"$FF" -y -hide_banner -loglevel error \
  -framerate 30 -i /tmp/frames/f%05d.jpg \
  -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 \
  -c:v libx264 -profile:v high -level 4.1 -preset slow -crf 20 \
  -pix_fmt yuv420p -r 30 -g 60 -movflags +faststart \
  -c:a aac -b:a 128k -shortest "$HERE/$NAME.mp4"
echo "fertig: $HERE/$NAME.mp4"
