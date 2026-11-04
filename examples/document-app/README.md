# 文件網站 fixture

這是合成資料用的唯讀 HTTP API，含 PostgreSQL 帳號與文件資料表、10 份附件、登入、搜尋及下載。僅供專用測試環境，不是正式服務。控制程式為 Go；此 Python 程式是被備份與恢復的應用。

完整備份、還原、報告與清理指令見 [M1 操作手冊](../../docs/M1_RUNBOOK.zh-TW.md)。建議使用 Go CLI 建立獨立環境；本目錄的 `compose.yaml` 僅保留為手動開發範例，不是 CLI 的設定輸入。CLI 使用自己的固定模板與所有權標籤。

```sh
python3 -m unittest discover -s examples/document-app -v
```

此單元測試以 fake storage 驗證 HTTP 與路徑行為。真正 PostgreSQL／Docker 的整合測試在 `tests/integration/m1.py`，與單元測試分開驗收。

- `app.py seed`：明確建立合成資料；已有文件會拒絕重建。寫入失敗可能留下附件，需重建本次 fixture volumes，不宣稱 DB/檔案初始化具原子性。
- `app.py serve`：不遷移、不 seed、不補回遺失附件；API 沒有資料寫入功能。
- `app.py reset-password`：明確將唯一 demo 帳號改為演練隨機密碼，報告記錄此差異。
- `smoke.py`：登入、搜尋、下載全部 10 份附件並核對 hash。
- `probe.py`：獨立回報 SQL、跨來源檔案、API 流程與指定外部端點的檢查狀態。

`/health` 只證明 DB 表可讀。附件不存在、不可讀、越界或 hash 不符時，下載回傳 409。Token 存在記憶體，15 分鐘失效；重啟需要重新登入。HTTP 無 TLS，僅限演練內網。
