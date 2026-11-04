# M1：文件網站備份與恢復演練

M1 僅支援自製 `document-app-v1`、PostgreSQL 17 custom-format dump，以及本工具製作的本機備份包。CLI 由允許清單產生 Compose 設定，不接受任意 Compose/YAML、正式備份或任意外部命令。M2 的 `doctor/plan --config` 尚未實作。

## 執行環境

在專用 Linux 測試環境操作；本次驗收為 WSL2 Ubuntu 24.04 x86-64。版本及映像 digest 見 [環境紀錄](ENVIRONMENT.zh-TW.md)。Docker 操作者須能存取本機 Unix socket。Windows PowerShell 可先執行 `wsl -d Ubuntu -u root -- bash`；接下來命令都在 Linux shell 執行。

```sh
cd /path/to/compose-recovery-lab
go test ./...
go vet ./...
go build -buildvcs=false -o bin/crl ./cmd/crl
python3 scripts/prepare-images.py
```

`-buildvcs=false` 避免 root 執行 Go build 時受到 Windows Git worktree 擁有者判定影響；不更動全域 Git safe.directory。映像先下載並建置，演練時只接受本機 immutable image ID/digest，停用自動 pull。下載／建置時間不包含在演練耗時內。

## 製作與恢復完整備份

```sh
bin/crl backup --out "$HOME/crl-demo/complete"
bin/crl run --bundle "$HOME/crl-demo/complete"
```

備份目的地必須不存在。`backup` 建立一組獨立來源環境、初始化 10 份合成文件、執行登入搜尋下載測試，停止唯讀應用後執行 `pg_dump` 和附件打包。成功或失敗都嘗試恢復應用，再清理本次來源資源。此命令不是任意現有服務的備份工具。

備份先寫入 `complete.partial`，完成檔案大小與 SHA-256 manifest 後以同一檔案系統的 rename 發布。失敗的 `.partial` 不會被 runner 接受；留存供診斷，不覆寫或刪除已有備份。備份包包含：

```text
manifest.json
database.dump
uploads.tar
app-config.sanitized.json
```

manifest 包含備份 ID、映像 ID/digest、PostgreSQL major、extension、時間區間、一致性方法、附件數量及各檔案大小與 hash。`app-config.sanitized.json` 是 fixture 的資訊紀錄，不是可執行設定。hash 不證明來源可信或原始資料完整。

`run` 先複製到新的私有工作目錄再驗證備份；接著建立全新的 DB、uploads volume、內網和應用容器。DB 應用角色不具 superuser/createdb/createrole，還原使用 `--no-owner --no-acl --single-transaction --exit-on-error`。帳號密碼在演練內明確替換成隨機值，此差異記入報告。

必要檢查：DB 恰有 10 筆文件且角色非 superuser、全量 DB 附件路徑與 SHA-256、API 登入搜尋及 10 份下載、指定外部 TCP 端點不可連線。這些結果只涵蓋合成 fixture，不代表所有業務功能或所有對外通道均受驗證。

## 缺附件故障案例

```sh
bin/crl backup --out "$HOME/crl-demo/missing" --omit-attachment
bin/crl run --bundle "$HOME/crl-demo/missing"
```

第二個命令預期回傳 1。故障包的 manifest 與 hash 正確，但刻意缺少一份 DB 引用的附件；SQL 通過，檔案關聯與 HTTP 下載失敗。報告不會從「缺檔」推論正式備份腳本的根因。

## 報告、取消與清理

CLI 印出 JSON 報告位置；同目錄有 HTML 報告和 `resources.json`。預設工作目錄是 Linux `$HOME/.local/state/compose-recovery-lab/runs/`，可用 `--work` 指定其他私有 Linux 目錄。不要放在多人共用或缺乏 Unix 權限保護的目錄。

- 每次演練持有帳號範圍的單執行鎖；同一帳號一次一個演練。
- 預設總逾時 10 分鐘，可用 `--timeout 2m` 調整；每個 Docker 操作上限 90 秒。
- Ctrl+C／SIGTERM 觸發取消；清理使用獨立的 60 秒期限。
- 驗證結果與清理結果分開記錄。必要檢查未執行會列為 skipped；驗證通過但清理失敗仍回傳非零。
- 先記錄 run intent，再建立有 run ID 及 Compose project 標籤的資源；清理先發現資源，再核對完整 ID（volume 使用其名稱）與兩項標籤。沒有 global prune，不刪除來源備份。
- SIGKILL／主機中斷不能執行 defer。重啟後用以下命令明確回收；不續跑半套 DB，也不把中斷演練標為成功。

```sh
bin/crl cleanup --run-dir /absolute/path/to/run-directory
```

清理可重試，成功後刪除含演練憑證的 Compose 工作檔和 staged 備份；報告及 journal 留存。備份產物與已下載映像保留供重跑，不屬於殘留演練容器資源。請自行決定報告與備份保留期限。

## 驗收與限制

```sh
python3 -m unittest discover -s examples/document-app -v
python3 tests/integration/m1.py
```

整合測試會建立真實容器、產生與還原真實 dump，並注入缺件、錯內容、hash 損壞、tar 越界、restore failure、備份失敗、取消、強制中斷及清理失敗。它先確認測試主機可連到外部基準端點，再確認演練內連線受阻。測試只清理自己建立的資源，並確認一個類似名稱的外部 sentinel volume 未變動。輸出的私有 evidence 目錄包含備份與每次報告，不提交 Git。

M1 的固定上限：單一備份檔 256 MiB、tar 展開總量 64 MiB、最多 10,000 個 entries；tar 拒絕絕對路徑、`..`、重複 entry、symlink/hardlink、特殊檔案及 setuid/setgid。僅支援合成 fixture 的一般附件與 UID/GID 10001；不宣稱保留任意正式資料權限。

每個服務有 CPU、記憶體、PID 上限；工作目錄至少保留 1 GiB 可用空間並每秒檢查。此為磁碟預檢與取消策略，不是 quota；Docker 儲存若位於另一個檔案系統，需另行監控。沒有主機 port、host bind mount、外部 volume/network。容器仍共享核心，不是惡意程式沙箱。

M2–M6 尚未完成：通用 YAML schema／doctor／plan、SQLite 狀態與歷史、完整各階段崩潰矩陣、自動重試、第二應用模板、通用 checker、Playwright、通知與跨主機部署。M1 不等於整個 P0 產品完成。
