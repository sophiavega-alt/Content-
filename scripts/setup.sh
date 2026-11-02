#!/usr/bin/env bash
# Installs the three video tools: FFmpeg, HyperFrames, yt-dlp.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v ffmpeg >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y ffmpeg
  elif command -v brew >/dev/null 2>&1; then
    brew install ffmpeg
  else
    echo "Install FFmpeg manually: https://ffmpeg.org/download.html" >&2; exit 1
  fi
fi

python3 -m pip install -r requirements.txt
npm install

echo
ffmpeg -version | head -1
echo "yt-dlp $(yt-dlp --version)"
echo "hyperframes $(npx hyperframes --version)"
