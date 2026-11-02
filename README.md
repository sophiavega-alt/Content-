# Content

Video editing toolkit — "The Only 3 Tools":

| Tool | Does | Installed via |
|---|---|---|
| [FFmpeg](https://ffmpeg.org) | Cuts + mixes video | system package (`apt`/`brew`) |
| [HyperFrames](https://github.com/heygen-com/hyperframes) | Captions + graphics (HTML → MP4) | npm (`hyperframes`, devDependency) |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Saves the Reels | pip (`requirements.txt`) |

## Setup

```bash
./scripts/setup.sh
```

## Quick examples

```bash
# Save a reel/video
yt-dlp -o "downloads/%(title)s.%(ext)s" "<url>"

# Cut 0:05–0:20 without re-encoding
ffmpeg -ss 5 -to 20 -i in.mp4 -c copy clip.mp4

# Start a captions/graphics composition, preview, render
npx hyperframes init my-video
npx hyperframes preview
npx hyperframes render
```
