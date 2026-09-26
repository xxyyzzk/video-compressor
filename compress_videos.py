# /// script
# requires-python = ">=3.10"
# dependencies = ["imageio-ffmpeg==0.6.0", "av>=14,<18"]
# ///
"""用 uv run compress_videos.py --help 查看使用方式。原檔永不修改。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

import av
import imageio_ffmpeg
from local_settings import defaults


EXTENSIONS = {".mov", ".mp4", ".mkv", ".m4v", ".avi", ".webm", ".mts"}
DEFAULT_INPUT, _ = defaults()


def interrupt_handler(signum, frame):
    raise KeyboardInterrupt


def inspect(path):
    with av.open(str(path)) as container:
        videos = [s for s in container.streams.video if not (s.disposition & s.disposition.attached_pic)]
        if not videos:
            raise ValueError(f"沒有可轉換的影像串流：{path}")
        video = videos[0]
        if video.index != container.streams.video[0].index:
            raise ValueError("第一個影像串流是封面圖，請先移除封面圖。")
        context = video.codec_context
        duration = float(video.duration * video.time_base) if video.duration else (
            container.duration / av.time_base if container.duration else 0
        )
        if duration <= 0:
            raise ValueError("無法取得影片長度。")
        return {
            "duration": duration,
            "width": context.width,
            "height": context.height,
            "pixel_format": context.format.name,
            "audio": [
                [s.codec_context.name, s.codec_context.sample_rate, s.codec_context.channels]
                for s in container.streams.audio
            ],
        }


def validate(source, target, expected_duration):
    result = inspect(target)
    for key in ("width", "height", "pixel_format", "audio"):
        if source[key] != result[key]:
            raise ValueError(f"驗證失敗：{key} 改變了（{source[key]} → {result[key]}）。")
    if abs(result["duration"] - expected_duration) > max(1.0, expected_duration * 0.001):
        raise ValueError("驗證失敗：輸出影片長度不符。")


def encode(ffmpeg, source, target, info, args, log):
    command = [ffmpeg, "-hide_banner", "-nostdin", "-n"]
    if args.start:
        command += ["-ss", str(args.start)]
    command += ["-noautorotate", "-i", str(source)]
    if args.sample:
        command += ["-t", str(args.sample)]
    command += [
        "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0",
        "-map_chapters", "-1" if args.sample else "0",
        "-c:v", "libx265", "-preset", args.preset,
        # '+' rejects automatic pixel-format conversion, including bit-depth loss.
        "-pix_fmt", "+" + info["pixel_format"],
        "-fps_mode", "passthrough", "-c:a", "copy",
        "-x265-params", "log-level=error" + (":lossless=1" if args.lossless else ""),
    ]
    if not args.lossless:
        command += ["-crf", str(args.crf)]
    if args.container in ("mp4", "mov"):
        command += ["-tag:v", "hvc1", "-movflags", "+faststart"]
    command += ["-progress", "pipe:1", "-nostats", str(target)]
    expected = min(args.sample or info["duration"], info["duration"] - args.start)
    started = time.monotonic()
    process = None
    with log.open("w", encoding="utf-8") as errors:
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True)
            for line in process.stdout:
                if line.startswith("out_time_us="):
                    try:
                        seconds = int(line.strip().split("=", 1)[1]) / 1_000_000
                    except ValueError:
                        continue
                    fraction = min(1.0, max(0.0, seconds / expected))
                    elapsed = time.monotonic() - started
                    eta = elapsed / fraction - elapsed if fraction else 0
                    print(f"\r  {fraction:6.1%}  已執行 {elapsed / 60:.1f} 分鐘  預估剩餘 {eta / 60:.1f} 分鐘", end="", flush=True)
            if process.wait() != 0:
                raise RuntimeError(f"FFmpeg 轉檔失敗，請查看 {log}")
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()
            print()
    validate(info, target, expected)


def main():
    parser = argparse.ArgumentParser(description="H.265 批次壓縮：保留解析度、時間戳、像素格式及所有原音訊。")
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT, help="影片或資料夾")
    parser.add_argument("-o", "--output", type=Path, help="輸出資料夾；預設為輸入資料夾中的 compressed")
    parser.add_argument("--crf", type=float, default=23, help="品質值，越低越清楚、越大（預設 23，與已確認的試壓設定相同）")
    parser.add_argument("--lossless", action="store_true", help="無損影像編碼；可能比原檔更大")
    parser.add_argument("--preset", choices=["fast", "medium", "slow", "slower"], default="slow", help="編碼速度（預設 slow）")
    parser.add_argument("--container", choices=["mp4", "mov", "mkv"], default="mp4", help="輸出容器（預設 mp4；PCM 音訊可用 mov 或 mkv）")
    parser.add_argument("--sample", type=float, metavar="SECONDS", help="只轉指定秒數，用來試壓")
    parser.add_argument("--start", type=float, default=0, metavar="SECONDS", help="試壓起點（預設 0）")
    parser.add_argument("--limit", type=int, help="最多處理幾部影片")
    parser.add_argument("--recursive", action="store_true", help="包含子資料夾，保留相對目錄")
    parser.add_argument("--dry-run", action="store_true", help="列出影片資訊，不產生輸出")
    args = parser.parse_args()
    if not 0 <= args.crf <= 51:
        parser.error("--crf 必須介於 0 到 51；CRF 0 仍不等於無損，無損請用 --lossless。")
    if args.start < 0 or (args.sample is not None and args.sample <= 0):
        parser.error("--start 不可小於 0，--sample 必須大於 0。")
    if args.start and args.sample is None:
        parser.error("--start 必須搭配 --sample，避免完整轉檔時意外截斷影片。")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必須大於 0。")
    args.input = args.input.expanduser().resolve()
    if not args.input.exists():
        parser.error(f"輸入路徑不存在：{args.input}")
    root = args.input if args.input.is_dir() else args.input.parent
    output = (args.output or root / "compressed").expanduser().resolve()
    if output == root:
        parser.error("輸出資料夾必須與輸入資料夾不同。")
    candidates = (root.rglob("*") if args.recursive else root.iterdir()) if args.input.is_dir() else [args.input]
    files = sorted(p for p in candidates if p.is_file() and p.suffix.lower() in EXTENSIONS
                   and not p.resolve().is_relative_to(output)
                   and (not args.input.is_dir() or not re.search(
                       r"\.h265-(?:crf\d+(?:\.\d+)?|lossless)-", p.name)))
    if args.limit:
        files = files[:args.limit]
    if not files:
        parser.error("找不到可處理的影片。")
    total = sum(p.stat().st_size for p in files)
    print(f"共 {len(files)} 部影片，{total / 1024**3:.2f} GiB；輸出：{output}")
    print("模式：" + ("影像無損（不保證縮小）" if args.lossless else f"高畫質 H.265，CRF {args.crf:g}（有損）") + "；音訊直接複製。")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    failures = 0
    for index, source in enumerate(files, 1):
        temporary = None
        print(f"\n[{index}/{len(files)}] {source.name}")
        try:
            info = inspect(source)
            print(f"  {info['width']}×{info['height']}，{info['duration'] / 60:.1f} 分鐘，音軌 {len(info['audio'])}")
            if args.start >= info["duration"]:
                raise ValueError("試壓起點超出影片長度。")
            if args.dry_run:
                continue
            mode = "lossless" if args.lossless else f"crf{args.crf:g}"
            suffix = f".sample-{args.start:g}-{args.sample:g}s" if args.sample else ""
            destination = output / source.relative_to(root).parent
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / f"{source.name}.h265-{mode}-{args.preset}{suffix}.{args.container}"
            receipt = target.with_suffix(target.suffix + ".json")
            settings = {
                "version": 1, "source": str(source), "size": source.stat().st_size,
                "mtime_ns": source.stat().st_mtime_ns, "crf": args.crf,
                "lossless": args.lossless, "preset": args.preset,
                "sample": args.sample, "start": args.start, "container": args.container,
            }
            signature = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
            if target.exists():
                saved = json.loads(receipt.read_text()) if receipt.exists() else {}
                if (saved.get("signature") == signature and saved.get("output_size") == target.stat().st_size
                        and saved.get("output_mtime_ns") == target.stat().st_mtime_ns):
                    print("  已完成且來源與設定相符，略過。")
                    continue
                raise FileExistsError(f"已有同名檔案但無相符的完成紀錄，為避免覆蓋請指定其他輸出資料夾：{target}")
            log = target.with_suffix(target.suffix + ".log")
            temporary = target.with_name(f".{target.stem}.{uuid.uuid4().hex}.partial{target.suffix}")
            encode(ffmpeg, source, temporary, info, args, log)
            # Hard-link promotion refuses to overwrite even if another process won the race.
            if os.name == "nt":
                # Windows rename refuses existing destinations and also supports exFAT.
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
                temporary.unlink()
            temporary = None
            size = target.stat().st_size
            record = {**settings, "signature": signature, "output_size": size,
                      "output_mtime_ns": target.stat().st_mtime_ns, "output": str(target)}
            receipt.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            if args.sample:
                print(f"  試壓完成：{size / 1024**2:.2f} MiB（片段大小不可直接與完整原檔比較）")
            else:
                print(f"  完成：{size / 1024**3:.2f} GiB，縮小 {(1 - size / source.stat().st_size):.1%}")
                if size >= source.stat().st_size:
                    print("  輸出未變小；原始檔案仍保留。")
            print(f"  {target}")
        except KeyboardInterrupt:
            print("\n已停止；原檔及先前完成的輸出均保留，下次執行會從未完成的影片重新開始。")
            return 130
        except Exception as error:
            failures += 1
            print(f"  錯誤：{error}", file=sys.stderr)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    print(f"\n處理結束；失敗 {failures} 部。原始檔案均未修改。")
    return 1 if failures else 0


if __name__ == "__main__":
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, interrupt_handler)
    sys.exit(main())
