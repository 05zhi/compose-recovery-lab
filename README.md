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

## 執行

建置需要 Go、GCC 與 Python 3；執行需要 Docker Engine 與 Compose。Windows 請在 WSL2 內執行。版本與安裝方式見[環境紀錄](docs/ENVIRONMENT.zh-TW.md)及[操作手冊](docs/OPERATIONS.zh-TW.md)。

在專用 Linux 測試環境、repo 根目錄，以同一個獲准存取 Docker 的帳號執行：

```sh
go build -buildvcs=false -o bin/crl ./cmd/crl
python3 scripts/prepare-images.py
bin/crl backup --out backups/complete
bin/crl doctor --config examples/document-app/drill.yaml
bin/crl plan --config examples/document-app/drill.yaml
bin/crl run --config examples/document-app/drill.yaml
bin/crl history --limit 10
```

備份目的地必須不存在。第二個模板、設定語法、歷史／恢復／retry、排程／通知及封裝方式見[操作與安裝手冊](docs/OPERATIONS.zh-TW.md)。映像準備需要網路，演練使用 immutable 本機映像，應用不發布 host ports。更新基底後需重新準備映像並建立新的合成備份；舊 bundle 保留原本的可信 image lock，不可直接改成新映像 ID。

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
