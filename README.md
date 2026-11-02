# Content

Video editing toolkit for editing with Claude.

| Tool | What it does in this workflow | Installed via | Repo |
|---|---|---|---|
| FFmpeg | Every cut, crop, mix, mute and render | system package (`apt`/`brew`) | https://github.com/FFmpeg/FFmpeg |
| faster-whisper | Word-level transcription that every cut is placed against | pip | https://github.com/SYSTRAN/faster-whisper |
| Whisper | OpenAI's speech model; faster-whisper runs it faster | models download automatically through faster-whisper; `WITH_OPENAI_WHISPER=1` installs the original package (large) | https://github.com/openai/whisper |
| yt-dlp | Downloads source videos (YouTube, TikTok, Reels) | pip | https://github.com/yt-dlp/yt-dlp |
| OpenCV + contrib | Follows the speaker for vertical crops (CSRT tracker is in contrib) | pip (`opencv-contrib-python-headless`) | https://github.com/opencv/opencv · https://github.com/opencv/opencv_contrib |
| Puppeteer | Drives headless Chrome to render HTML captions/titles and screenshots | npm | https://github.com/puppeteer/puppeteer |
| HyperFrames (HeyGen) | Motion graphics written in HTML, rendered to MP4 | npm | https://github.com/heygen-com/hyperframes |

## Setup

```bash
./scripts/setup.sh
```

## Quick examples

```bash
# Download a source video
yt-dlp -o "downloads/%(title)s.%(ext)s" "<url>"

# Cut 0:05–0:20 without re-encoding
ffmpeg -ss 5 -to 20 -i in.mp4 -c copy clip.mp4

# Word-level transcript
python3 -c "from faster_whisper import WhisperModel; m=WhisperModel('small', compute_type='int8'); \
[print(f'{w.start:.2f}-{w.end:.2f} {w.word}') for s in m.transcribe('clip.mp4', word_timestamps=True)[0] for w in s.words]"

# Captions/graphics composition
npx hyperframes init my-video && npx hyperframes preview && npx hyperframes render
```
