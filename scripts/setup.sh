#!/usr/bin/env bash
# Installs the video toolkit: FFmpeg, yt-dlp, faster-whisper (Whisper),
# OpenCV + contrib, Puppeteer, HyperFrames.
# Set WITH_OPENAI_WHISPER=1 to also install the original openai-whisper (large: pulls PyTorch).
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
if [ "${WITH_OPENAI_WHISPER:-0}" = "1" ]; then
  python3 -m pip install openai-whisper
fi
npm install

echo
ffmpeg -version | head -1
echo "yt-dlp $(yt-dlp --version)"
python3 -c "import faster_whisper, cv2; print('faster-whisper', faster_whisper.__version__); print('opencv', cv2.__version__)"
node -e "console.log('puppeteer', require('puppeteer/package.json').version)"
echo "hyperframes $(npx hyperframes --version)"
