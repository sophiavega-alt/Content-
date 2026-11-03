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


def motion_curve(path, rate=10):
    """Mean absolute frame difference, sampled `rate` times per second on tiny grayscale frames.

    Decoded by FFmpeg (multithreaded, applies phone rotation); cached next to the scratch output.
    """
    cache = Path(tempfile.gettempdir()) / f"motion_{Path(path).stem}_{Path(path).stat().st_size}.npy"
    if cache.exists():
        return np.load(cache), 1.0 / rate
    w, h = 72, 128
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-an", "-vf",
                          f"fps={rate},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    scores = np.concatenate([[0.0], np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))])
    np.save(cache, scores)
    return scores, 1.0 / rate


def best_window(scores, step, length, duration, edge=8.0, win=8.0):
    """Start of a length-second shot in the middle of the clearest run of reps.

    Reps are rhythmic: the motion signal repeats every ~1-5 s. Walking to/from the phone or
    re-racking is one big burst. So each `win`-second window is scored by how periodic its motion
    is (autocorrelation peak) times how much is moving, and the first/last `edge` seconds
    (phone handling) are skipped.
    """
    n = len(scores)
    wn = int(win / step)
    e = int(min(edge, duration * 0.15) / step)
    if n < wn + 2 * e + 2:
        return max(0.0, (duration - length) / 2), float(scores.mean()) if n else 0.0
    lags = np.arange(int(1.0 / step), int(5.0 / step))
    best, best_i = -1.0, e
    for i in range(e, n - e - wn, max(1, int(0.5 / step))):
        x = scores[i:i + wn]
        level = float(np.median(x))
        x = x - x.mean()
        denom = float((x * x).sum()) or 1.0
        ac = max(float((x[:-L] * x[L:]).sum()) / denom for L in lags)
        # penalise windows dominated by one huge burst (walking past the camera)
        burst = float(scores[i:i + wn].max()) / (level + 1e-3)
        score = max(ac, 0.0) * level / (1.0 + 0.1 * max(0.0, burst - 4.0))
        if score > best:
            best, best_i = score, i
    start = (best_i + wn / 2) * step - length / 2
    return max(0.0, min(start, duration - length)), best


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
    ap.add_argument("--pick", action="append", default=[], metavar="NAME=SECONDS",
                    help="force where a clip's shot starts, e.g. --pick IMG_1401=42.5 (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="only print which moments would be used")
    ap.add_argument("--slow", metavar="NAME", help="which clip gets the slow-motion shot")
    a = ap.parse_args()

    clips = []
    for p in map(Path, a.inputs):
        clips += sorted(x for x in p.iterdir() if x.suffix.lower() in VIDEO_EXT) if p.is_dir() else [p]
    if not clips:
        sys.exit("no clips found")

    picks_override = {k: float(v) for k, v in (x.split("=", 1) for x in a.pick)}
    shot = min(a.max_shot, max(a.min_shot, a.target / len(clips)))
    picks = []
    for c in clips:
        meta = probe(c)
        length = min(shot, meta["duration"])
        scores, step = motion_curve(c)
        start, energy = best_window(scores, step, length, meta["duration"])
        if c.stem in picks_override:
            start = picks_override[c.stem]
        picks.append({"path": c, "meta": meta, "start": start, "len": length, "energy": energy})
        print(f"{c.name}: {meta['duration']:.1f}s {meta['fps']:.0f}fps{' HDR' if meta['hdr'] else ''}"
              f" -> {start:.1f}s +{length:.1f}s (motion {energy:.1f})")

    slow = None
    if not a.no_slowmo:
        fast = [p for p in picks if p["meta"]["fps"] >= 50]
        if a.slow:
            fast = [p for p in fast if p["path"].stem == a.slow] or fast
        if fast:
            slow = max(fast, key=lambda p: p["energy"])
            slow["slow"] = True
            print(f"slow motion: {slow['path'].name}")

    if a.dry_run:
        return
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
