#!/bin/zsh
# Finder 雙擊，或在 Terminal 執行這個檔案。
SCRIPT_DIR="${0:A:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
UV_BIN="$(command -v uv)"
if [[ -z "$UV_BIN" ]]; then
    print "找不到 uv。請先安裝 uv，再開啟此檔案。"
    read -r "?按 Enter 關閉……"
    exit 1
fi
cd "$SCRIPT_DIR" || exit 1
"$UV_BIN" run --no-project --cache-dir "$SCRIPT_DIR/.uv-cache" "$SCRIPT_DIR/terminal_menu.py" "$@"
result=$?
if [[ -t 0 ]]; then
    read -r "?按 Enter 關閉視窗……"
fi
exit "$result"
