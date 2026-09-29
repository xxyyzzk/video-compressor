# Video Compressor｜MOV / MP4 影片壓縮

Python + uv 影片轉檔工具，預設輸出 **MP4 / H.265（HEVC）/ CRF 23 / slow**。支援 Windows 10/11 x64 與 macOS，MOV、MP4 可混合批次處理。

保留原解析度、畫格時間戳與所有原音訊，原始檔案永不修改或刪除。影片在自己的電腦處理，不上傳影片、不呼叫 AI API。畫面仍屬有損壓縮，壓縮率依內容而異，已壓得很小的影片可能轉得更大。

## Windows 開始使用

1. 登入有權限的 GitHub 帳號，按本儲存庫的 **Code → Download ZIP**，解壓縮到可寫入的資料夾，例如 `D:\Tools\video-compressor`。也可用 Git clone。
2. 開啟 PowerShell，安裝 uv：

   ```powershell
   winget install --id astral-sh.uv -e
   ```

3. 關閉並重新開啟 Terminal，使 PATH 更新。雙擊 **start_windows.bat**。
4. 啟動後會自動跳出資料夾選擇視窗，選擇放影片的資料夾，再進入轉檔選單。按取消會直接離開，不會使用舊來源或開始轉檔。
5. 輸入影片編號開始，或輸入 **A** 依序轉換所有待轉影片。

首次執行需要網路，uv 會自動下載 Python 3.12、套件與套件隨附的 FFmpeg。不必另裝 Python 或 FFmpeg，也不要在 ZIP 壓縮檔裡直接啟動。

若沒有 winget，參閱 [uv 官方安裝方式](https://docs.astral.sh/uv/getting-started/installation/)。主要支援 x64 Windows，Windows ARM64 未驗證。

## macOS

安裝 [uv](https://docs.astral.sh/uv/getting-started/installation/) 後雙擊 **開始轉檔.command**。若下載 ZIP 後無法雙擊，可在 Terminal 進入專案資料夾執行：

```bash
chmod +x 開始轉檔.command
./開始轉檔.command
```

## 互動選單

| 輸入 | 功能 |
| --- | --- |
| 影片編號 | 轉換該部完整影片 |
| A | 依序轉換待轉影片，略過已完成及有暫存檔的影片 |
| S | 再次跳出資料夾選擇視窗，不立即轉檔 |
| P | 貼上或拖入單一影片／資料夾的路徑 |
| R | 更新狀態 |
| O | 開啟輸出資料夾 |
| Q | 離開 |
| Ctrl+C | 停止選單本次啟動的作業並返回選單 |

未指定來源時，Windows 與 macOS 都會先顯示原生資料夾選擇視窗，輸出在所選來源內的 `compressed` 子資料夾；單一影片則使用它所在資料夾。選單會顯示完整輸出路徑。

若不方便使用視窗，可執行 `uv run terminal_menu.py --no-dialog` 改用輸入路徑。若啟動時已帶入來源（例如 `uv run terminal_menu.py "D:\Videos"`），會直接進入選單。視窗無法啟動時也會提供輸入路徑的備用方式。選單內取消選擇則保留目前來源。

轉檔時請保持 Terminal 開啟，勿讓電腦睡眠或將筆電闔蓋。macOS 選單會在轉檔期間暫時防止閒置睡眠，Windows 請自行調整電源設定。已由其他程式啟動的轉檔不受選單的 Ctrl+C 控制。

## 直接用 uv 執行

在 PowerShell 或 Terminal 切換到專案目錄：

```powershell
# 互動選單
uv run terminal_menu.py

# 一部 MOV 或 MP4，立即轉檔
uv run compress_videos.py "D:\Videos\lesson.mov"
uv run compress_videos.py "D:\Videos\lesson.mp4"

# 混合資料夾／指定輸出位置
uv run compress_videos.py "D:\Videos" -o "E:\Compressed"

# 先試壓：從第 120 秒開始取 5 分鐘，只處理第一部
uv run compress_videos.py "D:\Videos" --sample 300 --start 120 --limit 1

# 包含子資料夾／只列出資訊
uv run compress_videos.py "D:\Videos" --recursive
uv run compress_videos.py "D:\Videos" --dry-run
```

macOS 使用相同指令，替換為自己的來源路徑即可。檔名保留來源副檔名，同名的 `lesson.mov` 與 `lesson.mp4` 不會互相覆蓋。掃描資料夾時排除本程式命名的 H.265 成品；試壓檔名含 `sample`。

## 品質選擇

- 預設 CRF 23 / slow，兼顧大小與品質。
- 加 `--crf 18` 提高品質，通常檔案也較大。
- 加 `--preset medium` 加快編碼，壓縮效率可能降低。
- 加 `--lossless` 保留解碼後的影像像素，但檔案可能比原本更大。
- 音訊一律直接複製。若 MP4 不支援來源音訊（例如部分 PCM），程式會報錯，可改用 `--container mov` 或 `--container mkv`；不會偷偷轉成有損音訊。

播放器需支援 H.265。只轉第一個影像串流與所有音軌，不包含字幕及資料串流。編碼器不支援來源像素格式時會報錯，避免默默降低位元深度或色彩品質。

## 驗證、重跑與中斷

每部成品旁有 `.json` 完成紀錄和 `.log` 編碼紀錄。成功後核對解析度、像素格式、片長、音軌格式，再將暫存檔改成正式輸出。這是結構驗證，不是逐幀視覺品質保證。

來源、設定與輸出均吻合時會略過；既有檔案缺少相符紀錄時拒絕覆蓋。搬到另一台電腦後來源路徑或修改時間可能不同，不保證能沿用原電腦的完成紀錄。

`轉檔中／有未完成暫存` 表示找到 `.partial.mp4`，選單不會重複開始。若先前強制關閉或斷電，先確認沒有該影片的轉檔程序執行，再刪除對應暫存檔並重試。未完成的單部影片會從頭重做。直接用核心程式時，不要同時對同一來源啟動多份工作。

## 每台電腦的預設路徑（可選）

在專案根目錄建立 `settings.local.json`：

```json
{
  "source": "D:/Videos",
  "output": "E:/Compressed"
}
```

選單仍會先要求選擇來源；若選到此設定的 source，則沿用這裡的 output。核心程式使用此預設來源，輸出仍以 `-o` 或來源內的 `compressed` 決定。設定檔不加入 Git，各電腦可有不同設定。選單按 S 切換到其他來源時會重設為該來源的預設輸出位置。

## 測試

```bash
uv run test_compressor.py
uv run test_terminal_menu.py
```

GitHub Actions 在 Windows 與 macOS 執行測試：MOV／MP4 混合輸入、HEVC 輸出、音訊封包一致、無損畫格雜湊、原檔保留、重跑略過、同名檔保護、路徑處理、選單切換、跨程序鎖定。桌面播放器及中斷快捷鍵仍需在實際桌面環境確認。

儲存庫只收錄程式、說明和測試，排除所有影片、成品、快取、本機設定與紀錄。

參考：[uv 安裝文件](https://docs.astral.sh/uv/getting-started/installation/)、[Python 子程序文件](https://docs.python.org/3/library/subprocess.html)、[FFmpeg 文件](https://ffmpeg.org/ffmpeg.html)。
