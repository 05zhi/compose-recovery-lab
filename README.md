# Compose Recovery Lab

用實際還原與應用操作，驗證 Docker Compose 合成備份能否使用。

支援文件網站與庫存網站兩個受限模板：PostgreSQL 17 dump、附件、全新內網／volumes、SQL／檔案／關聯／HTTP／Chromium E2E 檢查、SQLite 歷史、崩潰回收、新 attempt 重試、JSON／HTML／錄影，以及依序排程與選用失敗通知。

實際完成項目、原始證據與尚未完成的外部試用條件，以[驗收紀錄](docs/M3_M6_ACCEPTANCE.zh-TW.md)為準。真實使用者回饋與大資料量效能驗證不可由合成 fixture 的成功推論。

## 執行

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

備份目的地必須不存在。第二個模板、設定語法、歷史／恢復／retry、排程／通知及封裝方式見[操作與安裝手冊](docs/OPERATIONS.zh-TW.md)。映像準備需要網路，演練使用 immutable 本機映像，應用不發布 host ports。

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
