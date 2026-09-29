# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""互動式 Terminal 選單；沿用 compress_videos.py 進行實際編碼。"""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import subprocess
import sys
from local_settings import defaults

BASE = Path(__file__).resolve().parent
DEFAULT_SOURCE, DEFAULT_OUTPUT = defaults()
SOURCE = DEFAULT_SOURCE
OUTPUT = DEFAULT_OUTPUT or DEFAULT_SOURCE / "compressed"
CACHE = BASE / ".uv-cache"
EXTENSIONS = {".mov", ".mp4", ".mkv", ".m4v", ".avi", ".webm", ".mts"}


def pick_folder():
    """Use native desktop dialogs without requiring Tk in uv's Python build."""
    if sys.platform == "darwin":
        script = '''try
return POSIX path of (choose folder with prompt "選擇要轉檔的影片資料夾")
on error number -128
return ""
end try'''
        command = ["/usr/bin/osascript", "-e", script]
    elif os.name == "nt":
        script = '''$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '選擇要轉檔的影片資料夾'
$dialog.ShowNewFolderButton = $false
try {
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::WriteLine($dialog.SelectedPath)
    }
} finally { $dialog.Dispose() }
'''
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        command = ["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", encoded]
    else:
        raise RuntimeError("這個系統沒有內建的資料夾選擇介面。")
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as error:
        raise RuntimeError(f"無法開啟資料夾選擇視窗：{error}") from error
    if result.returncode:
        raise RuntimeError("無法開啟資料夾選擇視窗，請改用貼上路徑。")
    value = result.stdout.rstrip("\r\n")
    return Path(value).resolve() if value else None


def select_source(output=None, text_only=False):
    """Return False on cancellation; never silently use an old folder."""
    if not text_only:
        print("請在跳出的視窗選擇影片資料夾……", flush=True)
        try:
            selected = pick_folder()
        except RuntimeError as error:
            print(error)
        else:
            if selected is None:
                return False
            configure(selected, output)
            return True
    raw = input("貼上或拖入影片／資料夾路徑（Enter 取消）：").strip()
    if not raw:
        return False
    configure(parse_path(raw), output)
    return True


def parse_path(value):
    """Accept literal paths, quoted paths, and one Finder-dragged shell path."""
    value = value.strip()
    literal = Path(value).expanduser()
    if value and literal.exists():
        return literal.resolve()
    # Preserve Windows backslashes in quoted Explorer paths, including UNC paths.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return Path(value[1:-1]).expanduser().resolve()
    if os.name == "nt":
        if not value:
            raise ValueError("請貼上一個影片或資料夾的完整路徑。")
        return Path(value).expanduser().resolve()
    try:
        parts = shlex.split(value)
    except ValueError as error:
        raise ValueError("路徑引號不完整，請重新貼上。") from error
    if len(parts) != 1:
        raise ValueError("請貼上一個影片或資料夾的完整路徑。")
    return Path(parts[0]).expanduser().resolve()


def configure(source, output=None):
    global SOURCE, OUTPUT
    source = source.expanduser().resolve()
    if not source.is_dir() and not (source.is_file() and source.suffix.lower() in EXTENSIONS):
        raise ValueError("請指定存在的影片或資料夾；支援 .mov、.mp4 等影片。")
    root = source if source.is_dir() else source.parent
    if output is None:
        output = DEFAULT_OUTPUT if root == DEFAULT_SOURCE and DEFAULT_OUTPUT else root / "compressed"
    output = output.expanduser().resolve()
    if output == root or (output.exists() and not output.is_dir()):
        raise ValueError("輸出必須是與來源資料夾不同的資料夾。")
    SOURCE, OUTPUT = source, output


def source_files():
    candidates = SOURCE.iterdir() if SOURCE.is_dir() else [SOURCE]
    return sorted(p for p in candidates if p.is_file() and p.suffix.lower() in EXTENSIONS
                  and not p.resolve().is_relative_to(OUTPUT)
                  and not re.search(r"\.h265-(?:crf\d+(?:\.\d+)?|lossless)-", p.name))


def target_for(source):
    return OUTPUT / f"{source.name}.h265-crf23-slow.mp4"


def status(source):
    target = target_for(source)
    relocated = source.parent / target.name
    existing = target if target.exists() else relocated
    if existing.exists():
        receipt = target.with_suffix(".mp4.json")
        try:
            record = json.loads(receipt.read_text(encoding="utf-8"))
            src_stat, dst_stat = source.stat(), existing.stat()
            if (record.get("source") == str(source.resolve())
                    and record.get("size") == src_stat.st_size
                    and record.get("mtime_ns") == src_stat.st_mtime_ns
                    and record.get("output_size") == dst_stat.st_size
                    and record.get("output_mtime_ns") == dst_stat.st_mtime_ns
                    and record.get("crf") == 23
                    and record.get("preset") == "slow"
                    and record.get("lossless") is False
                    and record.get("sample") is None
                    and record.get("start") == 0
                    and record.get("container") == "mp4"):
                return "已完成" if existing == target else "已完成（原資料夾）"
        except (OSError, ValueError, TypeError):
            pass
        return "已有輸出，需檢查"
    # Detect the already-running job too: it predates this menu's lock.
    prefix = f".{target.stem}."
    if OUTPUT.exists() and any(
        p.name.startswith(prefix) and p.name.endswith(".partial.mp4")
        for p in OUTPUT.iterdir()
    ):
        return "轉檔中／有未完成暫存"
    return "待轉檔"


def run_one(source):
    current = status(source)
    if current != "待轉檔":
        print(f"略過：{source.name}（{current}）", flush=True)
        return 0
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("找不到 uv，請先安裝 uv，Windows 可執行 winget install --id astral-sh.uv -e。")
    command = [uv, "run", "--no-project", "--cache-dir", str(CACHE),
               str(BASE / "compress_videos.py"), str(source),
               "--crf", "23", "--preset", "slow", "--container", "mp4",
               "-o", str(OUTPUT)]
    options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
               else {"start_new_session": True})
    process = subprocess.Popen(command, cwd=BASE, **options)
    awake = None
    try:
        # Prevent idle sleep only while this job is running. Do not prevent lid sleep.
        if sys.platform == "darwin" and Path("/usr/bin/caffeinate").exists():
            try:
                awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(process.pid)])
            except OSError:
                pass
        return process.wait()
    except KeyboardInterrupt:
        print("\n正在停止本次轉檔並清除暫存，請稍候……", flush=True)
        if process.poll() is None:
            try:
                if os.name == "nt":
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        return 130
    finally:
        if awake is not None:
            if awake.poll() is None:
                awake.terminate()
            awake.wait()


def menu():
    while True:
        files = source_files()
        print("\n=== MOV / MP4 影片轉檔 ===", flush=True)
        print("MP4 · H.265 · CRF 23 · slow · 保留原解析度與原音訊")
        print("畫面屬有損壓縮；原始影片保留。")
        print(f"來源：{SOURCE}")
        print(f"輸出：{OUTPUT}\n")
        if not files:
            print("沒有可轉換的來源影片，請按 S 更換來源。")
        for index, path in enumerate(files, 1):
            print(f"{index:2}. [{status(path)}] {path.name}")
        print("\nA. 依序轉換所有待轉檔影片")
        print("S. 開啟資料夾選擇視窗    P. 貼上影片或資料夾路徑")
        print("R. 更新狀態    O. 開啟輸出資料夾    Q. 離開")
        choice = input("\n輸入影片編號，或 A / S / P / R / O / Q：").strip().lower()
        if choice == "q":
            return 0
        if choice == "r":
            continue
        if choice in ("s", "p"):
            try:
                if not select_source(text_only=choice == "p"):
                    print("已取消選擇，保留目前來源。")
            except ValueError as error:
                print(f"無法更換來源：{error}")
            continue
        if choice == "o":
            OUTPUT.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(OUTPUT))
            else:
                subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(OUTPUT)], check=False)
            continue
        if choice == "a":
            selected = [path for path in files if status(path) == "待轉檔"]
        elif choice.isdecimal() and 1 <= int(choice) <= len(files):
            selected = [files[int(choice) - 1]]
        else:
            print("請輸入清單中的編號或選項。")
            continue
        if not selected:
            print("沒有待轉檔影片；已完成及有暫存檔的影片均略過。")
            continue
        for path in selected:
            result = run_one(path)
            if result == 130:
                print("已停止本次作業，返回選單。原始影片不受影響。")
                break
            if result:
                print("本次影片轉檔失敗，請查看上方錯誤或輸出資料夾中的 .log。")
                print("批次處理已停止，返回選單。")
                break
        else:
            print("本次處理結束。")


def acquire_lock(lock):
    if os.name == "nt":
        import msvcrt
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def main():
    parser = argparse.ArgumentParser(description="MOV / MP4 互動轉檔選單，統一轉成 MP4 / H.265 / CRF 23。")
    parser.add_argument("input", nargs="?", type=Path, help="可選：來源影片或資料夾")
    parser.add_argument("-o", "--output", type=Path, help="可選：輸出資料夾")
    parser.add_argument("--no-dialog", action="store_true", help="啟動時改用輸入路徑，不跳出視窗")
    args = parser.parse_args()
    try:
        if args.input is not None:
            configure(args.input, args.output)
    except ValueError as error:
        parser.error(str(error))
    # Persistent lock file; flock releases automatically when the process exits.
    with (BASE / ".terminal-menu.lock").open("a+b") as lock:
        try:
            acquire_lock(lock)
        except (BlockingIOError, PermissionError):
            print("已有轉檔選單開啟，請使用原本的 Terminal 視窗。")
            return 1
        try:
            if args.input is None:
                try:
                    selected = select_source(args.output, text_only=args.no_dialog)
                except ValueError as error:
                    print(f"無法選擇來源：{error}")
                    return 1
                if not selected:
                    print("已取消，未開始轉檔。")
                    return 0
            return menu()
        except (KeyboardInterrupt, EOFError):
            print("\n已離開選單。")
            return 0
        except (OSError, RuntimeError) as error:
            print(f"錯誤：{error}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
