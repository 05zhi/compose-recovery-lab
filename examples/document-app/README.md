# 文件網站 fixture（M1 第一部分）

這是合成資料用的 HTTP API，含 PostgreSQL 帳號與文件資料表、10 份附件、登入、搜尋及下載。僅供專用測試環境，不是正式服務或完整演練器。控制程式仍依計畫採 Go；此 Python fixture 是被還原的應用。

## 本機可執行檢查

```sh
cd examples/document-app
python -m unittest -v
```

單元測試使用 fake storage，實際啟動 HTTP server；不代表 PostgreSQL 或 Docker 已驗收。

## Linux Docker 整合驗收入口（尚未實測）

需 Docker Engine、Compose v2，先進入本目錄。映像 tag 與套件已指定版本，但尚未取得 digest 或完成 Linux 版本鎖定。不要將這個開發 compose 當成產品隔離保證。

```sh
export DEMO_DB_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
export DEMO_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
export COMPOSE_PROJECT_NAME=crl-demo-$(python3 -c 'import secrets; print(secrets.token_hex(8))')
# 以下僅限剛產生的專用測試 project；不要改成既有服務名稱。
trap 'docker compose down --volumes' EXIT
docker compose build
docker compose up -d --wait db
docker compose run --rm app python app.py seed
docker compose up -d app
# 等待 HTTP 就緒後，執行登入、搜尋、10 份下載及 hash 驗證。
docker compose exec -T app python -c 'import time,urllib.request; time.sleep(2); urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=10)'
docker compose exec -T app python smoke.py
```

需用 `bash -e` 執行上述流程，確保任一步失敗即停止且執行 EXIT trap。無主機 ports、host bind mounts 或外部 volumes，app 與 DB 僅在 internal network。映像建置/下載發生在應用啟動前。

`seed` 只允許明確執行，已有文件會拒絕重建。寫入失敗後可能留下附件，請重建專用 fixture volumes；不宣稱跨 DB/檔案的 seed 具原子性。服務 API 是唯讀，未提供上傳或帳號修改，因此沒有線上寫入需要暫停；備份腳本仍須停止應用、處理失敗恢復，再導出一致備份。

`/health` 只證明 DB 表可讀。附件不存在、不可讀、越界或內容 hash 錯誤時，下載回傳 409；不會從內建資料修復附件。登入 token 保存在記憶體，15 分鐘失效；重啟需要重新登入。HTTP 不含 TLS，僅限測試內網。

下一部分：備份製作器、manifest、完整與缺附件案例、Go runner、資源所有權核對、還原與清理驗收。此處的 trap 不處理 SIGKILL 或主機當機，不替代規劃中的持久化清理。
