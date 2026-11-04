# Compose Recovery Lab

Docker Compose 應用的自動還原演練工具，以實際恢復及應用下載驗證合成備份。

## 目前狀態

**M1／M2 已完成固定模板驗收。** 支援固定的文件網站 fixture：PostgreSQL 17 custom-format dump、10 份附件、本機備份包、全新環境恢復、登入搜尋下載、JSON/HTML 報告及資源清理。已提供嚴格版本化 YAML、doctor／plan 與設定驅動還原；完整 P0 尚未完成。

```sh
# 在專用 Linux 測試環境、repo 根目錄執行，需本機 Docker 權限。
go build -buildvcs=false -o bin/crl ./cmd/crl
python3 scripts/prepare-images.py
bin/crl backup --out backups/complete
bin/crl doctor --config examples/document-app/drill.yaml
bin/crl plan --config examples/document-app/drill.yaml
bin/crl run --config examples/document-app/drill.yaml

# 合法但缺少一份附件的備份；最後一行預期回傳非零。
bin/crl backup --out "$HOME/crl-demo/missing" --omit-attachment
bin/crl run --bundle "$HOME/crl-demo/missing"
```

backup／run 輸出報告路徑；doctor／plan 輸出 JSON。預設使用私有 Linux 工作目錄，備份目的地必須不存在。Ctrl+C 會取消並清理；SIGKILL 或主機中斷後可用 `bin/crl cleanup --run-dir RUN_DIRECTORY` 明確回收。

- [M2 設定與 doctor／plan 手冊](docs/M2_RUNBOOK.zh-TW.md)
- [M2 驗收紀錄](docs/M2_ACCEPTANCE.zh-TW.md)
- [M1 操作手冊與限制](docs/M1_RUNBOOK.zh-TW.md)
- [實際環境與版本](docs/ENVIRONMENT.zh-TW.md)
- [M1 驗收紀錄](docs/M1_ACCEPTANCE.zh-TW.md)
- [詳細計畫書](docs/OPERATIONS.zh-TW.md)
- [進度與 commit 紀錄](docs/M3_M6_ACCEPTANCE.zh-TW.md)
- [開發規範](AGENTS.md)

## 驗證

```sh
go test ./...
go vet ./...
python3 -m unittest discover -s examples/document-app -v
python3 tests/integration/m2.py
python3 tests/integration/m1.py
```

整合測試真的建立容器、還原資料並注入故障；需要已完成映像準備與 CLI build。測試會保留私有備份及報告，不提交 Git。

## 邊界

只接受使用者信任的固定合成模板；不接受任意 Compose、正式環境原地還原或任意資料庫版本。容器共享核心，內網不等於惡意程式沙箱。必要檢查未執行不算通過；驗證通過但清理失敗仍回傳非零。

M3–M6 的 SQLite 歷史、自動重試、第二應用、通用 checker 和通知仍待完成。M2 設定只接受已實作模板及固定檢查，不接受任意 Compose／SQL／來源改名。每個可驗收部分先檢查再 commit；push 與本機提交分開處理。
