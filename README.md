# Compose Recovery Lab

用實際還原與應用操作，驗證 Docker Compose 合成備份能否使用。

支援文件網站與庫存網站兩個受限模板：PostgreSQL 17 dump、附件、全新內網／volumes、SQL／檔案／關聯／HTTP／Chromium E2E 檢查、SQLite 歷史、崩潰回收、新 attempt 重試、JSON／HTML／錄影，以及依序排程與選用失敗通知。

## 目前可用程度

截至 2026-11-05，已是**可用的本機工程版本**，適合在專用測試環境進行合成資料演練與受控試用。已驗證環境為 WSL2 Ubuntu 24.04／Linux amd64；M1–M5 與 M6 的兩模板本機工程驗收已完成，真人獨立試用仍待回饋。

| 功能 | 已驗證範圍 |
|---|---|
| 備份與還原 | 文件、庫存兩個固定模板；PostgreSQL 17、附件及應用設定 |
| 設定與預檢 | 設定 schema、doctor／plan、manifest 與來源映射驗證 |
| 應用驗證 | SQL、檔案、關聯、HTTP，以及真實 Chromium 登入／搜尋／下載；庫存另含匯出驗證 |
| 證據與清理 | SQLite 歷史、JSON／HTML 報告、錄影、資源清理、中斷回收與全新 attempt 重試 |

最近一次修正後驗收通過 **40 次完整還原、840 次瀏覽器流程**，另通過 20 輪 libc 根因回歸、26 個整合情境、4 個原生訊號故障情境、12 次崩潰回收與 2 次 retry；最後演練資源零殘留。瀏覽器啟動時的環境變數競爭已透過 glibc 2.41 基底修正，沒有加入自動重試掩蓋失敗。詳見[根因與重複驗證紀錄](docs/BROWSER_INCIDENT.zh-TW.md)。

目前不支援任意 Docker Compose 專案或正式環境原地還原。其他平台、完整冷 VM、整機斷電／檔案系統損毀及正式資料尚未驗收；兩名真人獨立試用與需求訪談也未完成。合成測試成功不能推論正式環境可用性、大資料量效能或完整災難復原能力。

第一次使用建議先跑下方文件模板，再依[獨立試用流程](docs/TRIAL_GUIDE.zh-TW.md)驗證操作與報告是否清楚。接入自己的專案前，需確認符合支援的模板與備份契約；完整範圍以[驗收紀錄](docs/M3_M6_ACCEPTANCE.zh-TW.md)為準。

## 使用步驟導覽

先跑一次成功情境，再跑一次故意缺少附件的失敗情境。以下指令都在 **Linux／WSL 的 repo 根目錄**執行，並固定使用同一個獲准存取 Docker 的帳號；切換帳號會切換 SQLite 歷史與鎖。

### 1. 準備環境與映像

建置需要 Go、GCC 與 Python 3；執行需要 Docker Engine 與 Compose。Windows 使用者先在 PowerShell 進入 WSL，再切換到自己的 repo 目錄。若沿用本專案以 root 執行的本機測試環境，可使用：

```powershell
wsl -u root
```

以下是 Linux shell 指令：

```sh
# 先 cd 到自己的 compose-recovery-lab repo 根目錄
docker version
docker compose version
go build -buildvcs=false -o bin/crl ./cmd/crl
python3 scripts/prepare-images.py
```

映像準備需要網路，完成後會產生兩模板各自的 `images.lock.json`。演練只使用已鎖定的本機映像。已經準備好相同版本時可跳過重新建置；版本與安裝方式見[環境紀錄](docs/ENVIRONMENT.zh-TW.md)及[操作手冊](docs/OPERATIONS.zh-TW.md)。

### 2. 建立一份完整備份

```sh
bin/crl backup --template document-app-v1 --out backups/complete
```

這個命令會建立合成文件網站、匯出資料，然後清除臨時來源網站；不是讀取你現有的正式網站。預期退出碼為 `0`，並印出備份操作的 `report: .../report.json`。

| 備份檔案 | 用途 |
|---|---|
| `database.dump` | PostgreSQL 資料，包含 10 筆合成文件 |
| `uploads.tar` | 文件附件 |
| `app-config.sanitized.json` | 去除秘密的應用設定 |
| `manifest.json` | 檔案大小、SHA-256、映像與版本契約 |

**備份目的地必須不存在。** 如果 `backups/complete` 已存在，可直接拿它繼續演練，前提是保留相符的可信 image lock；要建立另一份備份，請改用新目錄，並同步調整 `examples/document-app/drill.yaml` 的 `backup.path`（相對於設定檔所在目錄）。更新基底後應重新準備映像並建立新備份，不可直接修改舊 manifest 的映像 ID。

### 3. 預檢環境與預覽計畫

```sh
bin/crl doctor --config examples/document-app/drill.yaml
bin/crl plan --config examples/document-app/drill.yaml
```

`doctor` 預期顯示 `ready: true`，確認設定、manifest、來源映射、磁碟空間、Docker 與本機映像。`plan` 列出還原來源、必要檢查及預計建立的資源，不執行還原，也不檢查環境可用性。範例設定的工作目錄是 `/var/tmp/compose-recovery-lab-runs`；需調整時修改 `runtime.work_dir`，不要放進備份目錄內。

### 4. 還原並驗證應用

```sh
bin/crl run --config examples/document-app/drill.yaml
echo "exit code: $?"
```

工具會依序執行預檢、備份 staging、資料庫與附件還原、啟動網站、必要檢查，以及資源清理。它使用全新的內部網路與 volumes，不發布 host ports；網站由檢查程式操作，演練結束即移除。

成功時退出碼為 `0`，終端機印出**這次還原**的 `report.json` 位置。每次 `run` 都建立新的 attempt，不覆寫之前的報告。範例會驗證 10 筆資料、10 份附件雜湊、HTTP 下載、Chromium 登入／搜尋／下載，以及指定外連端點是否被阻擋。

### 5. 查看報告、錄影與歷史

打開剛才 `run` 印出的 `report.json` 所在目錄，使用瀏覽器開啟同目錄的 `report.html`。先看以下項目：

| 報告欄位／檔案 | 成功情境應看到什麼 |
|---|---|
| `verification_result` | `passed`，必要檢查全部通過 |
| `cleanup_result` | `complete`，演練資源已清除 |
| `checks` | 每項檢查的狀態與證據；有覆蓋欄位時另核對實際檢查數 |
| `steps` | 各階段狀態與耗時 |
| `remaining_resources` | 沒有待清理資源 |
| `browser.webm` | 實際瀏覽器操作錄影；未進入瀏覽器流程時可能不產生 |

也可由歷史讀取結果。將下方 `ATTEMPT_ID` 換成該報告的 `attempt_id`：

```sh
bin/crl history --limit 10
bin/crl status --run ATTEMPT_ID --attempt
```

Windows／WSL 使用者可在 Linux shell 開啟報告所在資料夾，再查看 HTML 與影片。下方路徑請替換為這次輸出的位置：

```sh
REPORT_DIR='/實際的/attempt/目錄'
explorer.exe "$(wslpath -w "$REPORT_DIR")"
```

### 6. 故意缺少附件，觀察驗證失敗

另外建立一份故障備份，不修改前面成功的備份：

```sh
bin/crl backup --template document-app-v1 --omit-attachment \
  --out backups/missing-attachment
bin/crl run --bundle backups/missing-attachment
echo "exit code: $?"
```

`backups/missing-attachment` 也必須是新目錄。這裡使用 `--bundle` 直接選取故障備份，避免仍讀取範例設定中的 `backups/complete`；兩個命令預設使用文件模板的本機 image lock。退出碼請緊接著 `run` 讀取，預期為 `1`。

| 檢查 | 缺少 `document-01.txt` 時的預期結果 |
|---|---|
| `sql-documents` | `passed`，資料庫仍有 10 筆文件 |
| `database-files` | `failed`，證據包含 `category=missing-file` |
| `login-search-download` | `failed`，缺附件的下載回傳 HTTP `409` |
| `external-connectivity` | `passed`，指定外連端點被阻擋 |
| 整體驗證／清理 | `failed`／`complete` |

故障備份本身的 manifest 與檔案雜湊仍有效，因此若將設定指向它，`doctor` 可以通過；還原後的關聯與下載檢查才會抓出缺檔。這個情境在 HTTP 檢查就失敗，尚未啟動 Chromium，因此沒有 `browser.webm`，報告會保留診斷檔。打開**這次失敗的** HTML 報告，對照上一份成功報告。

### 7. 確認失敗後也清理完整

除了確認報告為 `cleanup_result: complete`，也可把下方值換成失敗報告的 `attempt_id`，獨立查詢 Docker：

```sh
ATTEMPT_ID='填入失敗報告的 attempt_id'
docker ps -aq --filter "label=io.compose-recovery-lab.run=$ATTEMPT_ID"
docker volume ls -q --filter "label=io.compose-recovery-lab.run=$ATTEMPT_ID"
docker network ls -q --filter "label=io.compose-recovery-lab.run=$ATTEMPT_ID"
bin/crl status --run "$ATTEMPT_ID" --attempt
```

前三個查詢沒有輸出，代表本次容器、volumes 與網路零殘留；`status` 應保留 `failed` 與 `complete`，不會因清理成功把驗證改成通過。備份、報告及歷史會保留。如果是程序遭強制中止或清理未完成，先執行 `bin/crl recover`，再重新檢查清理狀態；不要使用全域 Docker prune。

第二模板、設定語法、retry、排程／通知及封裝方式見[操作與安裝手冊](docs/OPERATIONS.zh-TW.md)。

## 開發檢查

```sh
go test -race ./...
go vet ./...
python3 -m unittest discover -s examples/document-app -p "test_*.py"
# 完整容器驗收命令見驗收紀錄；測試不使用正式資料。
```

## 能證明什麼

報告分開列出驗證與清理結果。必要檢查缺漏、skipped、error 或中斷不算通過；清理失敗仍回傳非零。抽樣報告列出 seed、母體、實際檢查數與未檢查數，不能把抽樣當成全部資料正確。

SIGKILL 後 `bin/crl recover` 對帳回收；下一次執行也先回收舊 attempt。retry 從新的資源完整還原，保留原來的 inconclusive／failed 紀錄。SQLite 不保存生成的密碼，完成清理後移除暫時 Compose 檔。

只接受可信的固定模板與操作員宣告，不接受任意 Compose 或正式環境原地還原。容器共享核心，內網不是惡意程式沙箱；單一外連端點測試也不是全面網路安全保證。實測時間不是 RTO 保證。

- [完整驗收與限制](docs/M3_M6_ACCEPTANCE.zh-TW.md)
- [瀏覽器間歇性失敗根因與修正](docs/BROWSER_INCIDENT.zh-TW.md)
- [操作與安裝](docs/OPERATIONS.zh-TW.md)
- [第二模板](examples/inventory-app/README.md)
- [架構與決策](docs/adr/0004-durable-adapters.md)
- [獨立試用流程](docs/TRIAL_GUIDE.zh-TW.md)
- [計畫書](docs/OPERATIONS.zh-TW.md)
- [進度與 commit](docs/M3_M6_ACCEPTANCE.zh-TW.md)
- [M1 驗收](docs/M1_ACCEPTANCE.zh-TW.md)／[M2 驗收](docs/M2_ACCEPTANCE.zh-TW.md)

每個可驗收部分獨立 commit；本機 commit 與 push 分開處理。
