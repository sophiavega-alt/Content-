#!/usr/bin/env python3
"""Workout video in the 'gym TikTok' style: real-time sets with a small exercise label on each.

Reads a JSON edit plan and renders a vertical 1080x1920 MP4:
  * each shot plays in real time (full reps, no slow motion)
  * a small lowercase label in TikTok Sans sits on the shot (like the in-app text tool)
  * clean, natural colour with a touch of warmth; hard cuts; short fade in/out
  * no audio, so you can add a trending sound in TikTok

Plan format (times in seconds of the source clip):
{
  "clips_dir": "downloads/gym",
  "shots": [
    {"clip": "IMG_1399.mp4", "start": 15.0, "dur": 3.0, "label": "upper day", "style": "intro"},
    {"clip": "IMG_1398.mp4", "start": 128.6, "dur": 3.8, "label": "lateral raise"}
  ]
}

Usage:
  python3 scripts/workout_edit.py plan.json -o renders/upper_day.mp4
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

W, H, FPS = 1080, 1920, 30
REPO = Path(__file__).resolve().parent.parent
DEFAULT_FONT = REPO / "assets" / "fonts" / "TikTokSans-Medium.ttf"
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

NATURAL = ",".join([
    "eq=contrast=1.04:saturation=1.03:gamma=1.03",
    "colorbalance=rm=0.025:bm=-0.02:rh=0.015:bh=-0.015",  # a touch warmer
])

STYLES = {  # font size and vertical position (fraction of height) for the label
    "label": (46, 0.60),
    "intro": (54, 0.42),
}


def esc(text):
    return text.replace("\\", "\\\\").replace("'", "’").replace(":", "\\:").replace("%", "\\%")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{r.stderr[-2000:]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("-o", "--out", default="renders/workout.mp4")
    ap.add_argument("--clips-dir", help="overrides clips_dir in the plan")
    ap.add_argument("--font", default=str(DEFAULT_FONT if DEFAULT_FONT.exists() else FALLBACK_FONT))
    a = ap.parse_args()

    plan = json.loads(Path(a.plan).read_text())
    clips_dir = Path(a.clips_dir or plan.get("clips_dir", "."))
    shots = plan["shots"]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        t_total = sum(s["dur"] for s in shots)
        for i, s in enumerate(shots):
            vf = [f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1",
                  f"fps={FPS}", NATURAL]
            if s.get("label"):
                size, ypos = STYLES[s.get("style", "label")]
                # fade the label in only when the exercise changes (not on a second angle of the same one)
                new = i == 0 or shots[i - 1].get("label") != s["label"]
                alpha = "if(lt(t,0.25),t/0.25,1)" if new else "1"
                vf.append(f"drawtext=fontfile='{a.font}':text='{esc(s['label'])}':fontsize={size}:"
                          f"fontcolor=white:x=(w-text_w)/2:y=h*{ypos}-text_h/2:"
                          f"shadowcolor=black@0.45:shadowx=0:shadowy=2:alpha='{alpha}'")
            if i == 0:
                vf.append("fade=t=in:st=0:d=0.3")
            if i == len(shots) - 1:
                vf.append(f"fade=t=out:st={max(0, s['dur'] - 0.5):.2f}:d=0.5")
            vf.append("format=yuv420p")
            part = Path(tmp) / f"{i:03d}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s['start']:.3f}", "-i", str(clips_dir / s["clip"]),
                 "-t", f"{s['dur']:.3f}", "-an", "-vf", ",".join(vf),
                 "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "14M", "-bufsize", "28M",
                 "-profile:v", "high", "-g", "60", "-color_primaries", "bt709", "-color_trc", "bt709",
                 "-colorspace", "bt709", str(part)])
            parts.append(part)
            print(f"{i + 1}/{len(shots)} {s['clip']} {s['start']:.1f}s +{s['dur']:.1f}s  {s.get('label', '')}")
        lst = Path(tmp) / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", "-movflags", "+faststart", str(out)])
    print(f"done: {out} ({t_total:.1f}s, {out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
