# M1 實測環境

2026-11-04 安裝於既有 WSL2 Ubuntu，沒有安裝 Windows Docker Desktop。

| 元件 | 實際版本 |
|---|---|
| Ubuntu | 24.04.2 LTS（noble），x86-64 |
| 核心 | 5.15.167.4-microsoft-standard-WSL2 |
| Go | go1.22.2 linux/amd64（Ubuntu 安全更新套件） |
| Docker Engine / CLI | 29.1.3，API 1.52 |
| Compose | 2.40.3+ds1-0ubuntu1~24.04.1 |
| containerd / runc | 2.2.1 / 1.3.4 |
| PostgreSQL | 17.6-bookworm；執行時以 digest 固定 |
| Python 容器 | 3.12.12-slim-bookworm；Dockerfile 固定 digest |
| psycopg | 3.3.7 |

安裝命令（Ubuntu 提供的套件，不代表最新版）：

```sh
apt-get update
apt-get install -y golang-go docker.io docker-compose-v2
systemctl start docker
go version
docker version
docker compose version
```

在 PowerShell 可用 `wsl -d Ubuntu -u root -- bash` 進入安裝與驗收環境；Docker 使用本機 Unix socket，沒有開啟 TCP API，也沒有把一般使用者加入 docker 群組。Docker systemd 服務由套件設為自動啟動。

PostgreSQL digest：`sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3`。

Python digest：`sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c`。

應用映像以本機建置結果的 immutable image ID 固定；`scripts/prepare-images.py` 產生不提交的 `examples/document-app/images.lock.json`。報告與 manifest 記錄這個 ID。重建後若 ID 改變，需重新製作 fixture 備份；不可用新映像冒充舊備份版本。

參考：[Docker Ubuntu 安裝](https://docs.docker.com/engine/install/ubuntu/)、[Go releases](https://go.dev/dl/)。本次實際採用 Ubuntu 發行套件，沒有宣稱是 Docker 官方 APT repo 安裝。


## M3–M6 增補

- SQLite Go driver：github.com/mattn/go-sqlite3 v1.14.32；CGO／GCC 編譯，執行檔限已驗證的 Linux amd64／glibc 環境。
- Playwright Python：1.58.0；Chromium headless shell 與 ffmpeg 在映像準備階段安裝。兩個 adapter 都固定建置後 image ID。
- `scripts/prepare-images.py` 產生 document-app 與 inventory-app 各自的 images.lock.json。建置 context 只複製明確允許的檔案，不包含來源備份或 reports。
- 本機套件解壓與新 HOME 驗收使用既有可信映像快取；沒有把它描述成另一台全新 VM 的安裝結果。
