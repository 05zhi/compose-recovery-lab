# 操作手冊：兩個受限模板

適用於專用 Linux 測試主機。已驗證環境為 WSL2 Ubuntu 24.04、Go 1.22.2（CGO 啟用）、GCC、Docker Engine 29.1.3、Compose 2.40.3。Docker 存取權等同主機高權限；只使用可信映像與合成備份。沒有安裝排程或對外通知服務。

## 安裝與第一個演練

建置需要 Go、GCC 與 Python 3；執行需要 Linux glibc、Docker 與 Compose。Windows 請在 WSL2 內執行，勿將 workspace 放進備份目錄。

```sh
go test ./...
go build -buildvcs=false -o bin/crl ./cmd/crl
python3 scripts/prepare-images.py
bin/crl backup --out backups/complete
bin/crl doctor --config examples/document-app/drill.yaml
bin/crl plan --config examples/document-app/drill.yaml
bin/crl run --config examples/document-app/drill.yaml
```

映像準備階段需要網路；演練只使用已鎖定的本機映像。Python base 與 PostgreSQL 固定 digest，Playwright 固定 1.58.0；本機 image lock 保存建置後 immutable ID，不提交 Git。重新建置後請重新製作 fixture；舊備份只能搭配它自己的可信 image lock。

第二模板有產品、兩個倉庫、12 筆庫存關聯與六份巢狀規格附件，額外驗證 CSV 彙總匯出：

```sh
bin/crl backup --template inventory-app-v1 \
  --images examples/inventory-app/images.lock.json --out backups/inventory-complete
bin/crl run --config examples/inventory-app/drill.yaml
```

備份目錄必須不存在。設定範例使用 `/var/tmp` 工作目錄，請依執行帳號調整。來源角色固定為 database.dump、uploads.tar 與 app-config.sanitized.json；這不是任意 Compose 引擎。

## 取消、恢復與歷史

```sh
bin/crl history --limit 20
bin/crl status --run ATTEMPT_ID
bin/crl status --run ATTEMPT_ID --attempt
bin/crl recover
bin/crl retry --run ATTEMPT_ID --config /absolute/path/drill.yaml
bin/crl report --run ATTEMPT_ID --attempt --format html > report.html
```

Ctrl+C／SIGTERM 取消執行，清理另有 60 秒預算；失敗診斷另限 10 秒。一般 Docker 操作上限 90 秒，pg_dump／pg_restore 上限 10 分鐘，皆不能超過設定的總逾時。SIGKILL 後執行 recover，或啟動下一個演練時自動對帳回收。retry 要求相同設定 hash，重新驗證來源，建立全新 attempt，保留舊報告；不接續部分還原的 DB。status 預設取同一 logical run 最新 attempt，`--attempt` 選定原始紀錄。

SQLite 位於執行帳號 `~/.local/state/compose-recovery-lab/history.sqlite3`。切換帳號會切換歷史與鎖，請固定一個操作帳號。所有權清理只核對本次 run 標籤與 resource ID，不做全域 prune。若回收失敗，新演練會被阻擋，先修復 Docker／權限後重試 recover。

報告由 SQLite 保存；即使 HTML 檔不存在仍可重新輸出。報告包含 phase 時間、設定 hash、映像、DB 版本、主機 CPU／記憶體／工作磁碟資訊、檢查證據、覆蓋與清理結果。失敗時的 diagnostics.json 只保留容器狀態、exit code／OOM 狀態及固定安全日誌訊息，其他行以 redacted 取代，不保留 SQL 或原始例外。錄影留在 attempt 目錄的 browser.webm；中斷或舊映像未產生影片時會列出限制。

## 自訂檢查

保留模板四項必要檢查，再附加下列宣告。最多 32 項，ID 必須唯一，未支援欄位直接拒絕。

```yaml
  - id: document-count
    type: sql
    required: true
    query: SELECT count(*) FROM documents
    expect: {operator: eq, value: 10}
  - id: attachment-sample
    type: database_files
    required: true
    query: SELECT storage_path, sha256 FROM documents
    root: uploads
    scope: {mode: sample, size: 3, seed: 42}
  - id: readiness
    type: http
    required: true
    path: /health
    status: 200
    contains: ready
```

執行資源：DB 為 512 MiB／128 PIDs，應用與 Chromium 為 768 MiB／256 PIDs，各限制 1 CPU。應用啟用 init 回收子程序、唯讀 rootfs 與 256 MiB 私有 tmpfs；不使用 host IPC。

SQL 只接受 SELECT，用獨立 crl_check 角色、唯讀交易、5 秒 statement timeout；禁止建立暫存表，僅授予 public schema 既有資料表 SELECT。scalar 最多一列一欄；關聯檢查最多 10,000 列，結果總字元上限 1 MiB。SQL 字串及回傳字串不出現在錯誤或報告。這是可信操作員的查詢工具，不是對惡意 SQL 的完整沙箱。

`database_files` 每列必須是 `(relative_path, sha256)`，可用 `scope: {mode: all}`。抽樣固定 seed、先排序再選取，報告列出母體、實際檢查數、未檢查數；提前失敗只計入實際嘗試的檔案。`file` 使用 root: uploads、path 與 64 位十六進位 sha256。單一檔案檢查上限 64 MiB。

HTTP 只能 GET 應用本身的相對路徑，禁止 redirect、外部 URL，5 秒 timeout、1 MiB body 上限。瀏覽器 E2E 是模板固定流程，不能由設定注入任意程式。

任何已知 assertion 失敗為 failed。必要檢查缺漏／skipped／error 為 inconclusive，取消為 canceled。驗證與清理分別記錄；驗證通過但清理失敗仍非零 exit。

## 排程與通知

```sh
python3 scripts/scheduled.py --binary /absolute/path/bin/crl \
  /absolute/path/document.yaml /absolute/path/inventory.yaml
bin/crl notify --run FAILED_ATTEMPT_ID
bin/crl notify --run FAILED_ATTEMPT_ID --webhook-file /private/webhook.url
```

排程依序執行，任一失敗回傳非零，仍執行後續設定。參考 examples/scheduling 的 cron／systemd 範例，手動安裝並確認帳號權限。未指定 webhook-file 時只輸出 JSON；成功不產生失敗事件。webhook 檔須為私有 regular file（0600），內容為已授權 HTTPS URL；HTTP 僅允許 loopback。拒絕 redirect，10 秒逾時，傳送內容僅版本、attempt ID、驗證與清理結果，不包含原始錯誤、備份路徑或憑證。Idempotency-Key 為 attempt ID；接收端應去重。投遞失敗有非零 exit，可手動重試，未實作背景佇列。

## 封裝與保留

```sh
python3 scripts/package.py --output /new/private/release-directory
# 在同目錄核對，再解壓到新的目錄：
sha256sum -c SHA256SUMS
tar -xzf compose-recovery-lab-COMMIT-linux-amd64.tar.gz
```

套件包含 Linux amd64 執行檔與已追蹤原始碼／文件，不含 image lock、備份、日誌或秘密。先在目標主機重新準備映像，CGO 執行檔需相容 glibc；其他平台未驗證。建立新的 history／work 目錄可驗證乾淨安裝流程，不能將共用暖映像快取說成全新 VM 驗證。

歷史不自動刪除。建議依內部政策保留私有報告／錄影 30 天；先確認 cleanup=complete 再由操作員封存已完成 attempt。工具不自動刪除來源備份。完成清理後刪除暫時 compose 設定；SQLite 與報告不保存生成的密碼。

## 效能量測

```sh
python3 scripts/benchmark.py --output "$HOME/crl-benchmark-new"
python3 scripts/benchmark-replay.py --cache warm \
  --fixture "$HOME/crl-benchmark-new" --output "$HOME/crl-warm-new"
python3 scripts/benchmark-replay.py --cache cold \
  --fixture "$HOME/crl-benchmark-new" --output "$HOME/crl-cold-input-new"
```

每個輸出目錄必須不存在。負載為 100 MiB／1 GiB 邏輯 PostgreSQL payload，停用該欄位 TOAST 壓縮、保留 dump 壓縮；不是 1 GiB 附件或不可壓縮備份。每組三次，保留原始階段時間及資料大小。檢查總列數、總位元組數、第一筆 payload 與所有既有應用流程，不宣稱逐位元組檢查全部 benchmark payload。

warm 會先讀取指定備份檔；cold 只對這些合成輸入檔使用 posix_fadvise，再用 mincore 確認執行前頁面不在記憶體。不清空全機 cache，兩組都沿用本機映像快取；因此不是冷 VM／冷映像測試。replay 另以 0.1 秒間隔取樣工作目錄及 Docker 所在檔案系統用量差，這是觀察值，可能受其他主機工作影響，不是硬性磁碟 quota 或峰值保證。實測結果見驗收紀錄。
