#!/usr/bin/env python3
"""Aesthetic workout montage for TikTok/Reels.

Takes a folder (or list) of raw gym clips and makes one vertical 1080x1920 video:
  * picks the highest-motion moment of each clip (the actual reps, not the setup)
  * slows the single most intense moment to 0.5x (when the source is 50+ fps)
  * warm, faded film grade with soft grain and a light vignette
  * converts iPhone HDR (HLG / Dolby Vision) to normal SDR so colours don't wash out
  * optional small serif title, fade in/out, no audio (add a trending sound in-app)

Usage:
  python3 scripts/montage.py downloads/gym/ -o renders/gym_montage.mp4 --title "leg day"
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

W, H, FPS = 1080, 1920, 30
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".hevc", ".mkv", ".webm"}
FONT = "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd[:6])}...\n{r.stderr[-2000:]}")
    return r.stdout


def probe(path):
    info = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height,avg_frame_rate,color_transfer:stream_side_data=rotation"
                           ":format=duration", "-of", "json", str(path)]))
    s = info["streams"][0]
    num, den = (s.get("avg_frame_rate") or "30/1").split("/")
    rot = 0
    for sd in s.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    w, h = s["width"], s["height"]
    if abs(rot) in (90, 270):
        w, h = h, w
    return {
        "duration": float(info["format"]["duration"]),
        "fps": float(num) / float(den or 1),
        "hdr": s.get("color_transfer") in ("arib-std-b67", "smpte2084"),
        "w": w, "h": h,
    }


def motion_curve(path, step_s=0.1):
    """Mean absolute frame difference sampled every step_s seconds (low-res, grayscale)."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    stride = max(1, round(fps * step_s))
    prev, scores, i = None, [], 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % stride == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(cv2.resize(frame, (90, 160)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            scores.append(0.0 if prev is None else float(np.mean(np.abs(g - prev))))
            prev = g
        i += 1
    cap.release()
    return np.array(scores), stride / fps


def best_window(scores, step, length, duration, margin=0.4):
    """Start time of the length-second window with the most motion (skipping start/end handling)."""
    n = max(1, int(round(length / step)))
    lo, hi = int(margin / step), len(scores) - n - int(margin / step)
    if hi <= lo or len(scores) < n:
        return max(0.0, (duration - length) / 2), float(scores.mean()) if len(scores) else 0.0
    sums = np.convolve(scores, np.ones(n), "valid")[lo:hi + 1]
    k = int(np.argmax(sums))
    return (lo + k) * step, float(sums[k] / n)


def frame_filter(meta):
    f = []
    if meta["hdr"]:
        f.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                 "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
    # fill 9:16 (crop centre if the clip is landscape)
    f.append(f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1")
    return f


GRADE = ",".join([
    "curves=all='0/0.05 0.25/0.24 0.75/0.78 1/0.95'",           # faded blacks, soft highlights
    "eq=contrast=0.96:saturation=0.82:gamma=1.02",
    "colorbalance=rs=0.04:bs=-0.04:rm=0.03:bm=-0.02:rh=0.02:bh=-0.03",  # warm
    "vignette=angle=PI/5",
    "noise=alls=5:allf=t",                                      # film grain
])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="clips or folders of clips")
    ap.add_argument("-o", "--out", default="renders/montage.mp4")
    ap.add_argument("--target", type=float, default=24, help="approx. total length in seconds")
    ap.add_argument("--min-shot", type=float, default=1.2)
    ap.add_argument("--max-shot", type=float, default=3.0)
    ap.add_argument("--title", default="", help="small serif title shown at the start")
    ap.add_argument("--no-slowmo", action="store_true")
    a = ap.parse_args()

    clips = []
    for p in map(Path, a.inputs):
        clips += sorted(x for x in p.iterdir() if x.suffix.lower() in VIDEO_EXT) if p.is_dir() else [p]
    if not clips:
        sys.exit("no clips found")

    shot = min(a.max_shot, max(a.min_shot, a.target / len(clips)))
    picks = []
    for c in clips:
        meta = probe(c)
        length = min(shot, meta["duration"])
        scores, step = motion_curve(c)
        start, energy = best_window(scores, step, length, meta["duration"])
        picks.append({"path": c, "meta": meta, "start": start, "len": length, "energy": energy})
        print(f"{c.name}: {meta['duration']:.1f}s {meta['fps']:.0f}fps{' HDR' if meta['hdr'] else ''}"
              f" -> {start:.1f}s +{length:.1f}s (motion {energy:.1f})")

    slow = None
    if not a.no_slowmo:
        fast = [p for p in picks if p["meta"]["fps"] >= 50]
        if fast:
            slow = max(fast, key=lambda p: p["energy"])
            slow["slow"] = True
            print(f"slow motion: {slow['path'].name}")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, p in enumerate(picks):
            vf = frame_filter(p["meta"])
            if p.get("slow"):
                vf.append("setpts=2*PTS")  # 60fps source -> real 0.5x slow motion at 30fps
            vf.append(f"fps={FPS},format=yuv420p")
            part = Path(tmp) / f"{i:03d}.mp4"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{p['start']:.3f}", "-t", f"{p['len']:.3f}",
                 "-i", str(p["path"]), "-an", "-vf", ",".join(vf),
                 "-c:v", "libx264", "-preset", "fast", "-crf", "14", str(part)])
            parts.append(part)
        lst = Path(tmp) / "list.txt"
        lst.write_text("".join(f"file '{x}'\n" for x in parts))
        total = sum(p["len"] * (2 if p.get("slow") else 1) for p in picks)

        vf = [GRADE, "fade=t=in:st=0:d=0.4", f"fade=t=out:st={max(0, total - 0.6):.2f}:d=0.6"]
        if a.title:
            t = a.title.replace("\\", "\\\\").replace("'", "’").replace(":", "\\:")
            vf.append(f"drawtext=fontfile={FONT}:text='{t}':fontsize=64:fontcolor=white:"
                      f"x=(w-text_w)/2:y=h*0.80:shadowcolor=black@0.35:shadowx=0:shadowy=2:"
                      f"alpha='if(lt(t,0.4),0,if(lt(t,1.0),(t-0.4)/0.6,if(lt(t,2.8),1,if(lt(t,3.4),(3.4-t)/0.6,0))))'")
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-an",
             "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "14M", "-bufsize", "28M", "-profile:v", "high",
             "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
             "-movflags", "+faststart", str(out)])
    print(f"done: {out} ({total:.1f}s, {out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
