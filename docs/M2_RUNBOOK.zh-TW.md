# M2：設定、doctor、plan 與來源映射

M2 以版本化設定連接 M1 的固定模板。支援 `document-app-v1`／PostgreSQL 17、本機完整備份包與四個既有必要檢查。自訂 SQL、任意 Compose、其他資料庫與第二模板仍不接受；M4／M6 另行實作。

## 快速執行

在具有本機 Docker 權限的專用 Linux x86-64 環境、repo 根目錄操作：

```sh
go build -buildvcs=false -o bin/crl ./cmd/crl
python3 scripts/prepare-images.py
bin/crl backup --out backups/complete
bin/crl doctor --config examples/document-app/drill.yaml
bin/crl plan --config examples/document-app/drill.yaml
bin/crl run --config examples/document-app/drill.yaml
```

備份目錄必須不存在；若已製作過，直接使用既有包或在 YAML 指定另一份包。範例 runtime workspace 是 Linux `/var/tmp/compose-recovery-lab-runs`。若已存在，必須是操作者可寫且沒有 group/other 權限的私有目錄；doctor 只查核，不替使用者建立或修改權限。

完整 YAML 見 [範例設定](../examples/document-app/drill.yaml)，編輯器與 CLI 共用 [JSON Schema](../internal/config/schema.json)。Schema 以 Go embed 編入 binary，不從網路或備份載入外部 schema。

## 設定契約

| 欄位 | 支援值／規則 |
|---|---|
| `schema_version` | 整數 `1` |
| `name` | 小寫英文字母開頭，最多 63 個小寫字母、數字或連字號 |
| `template` | `document-app-v1` |
| `backup.type` | `local_bundle` |
| `backup.path` | 已完成的備份目錄；不接受 `.partial` |
| `backup.mapping` | 必須完整對應下表三種角色，不能重新指定正式路徑或外部 volume |
| `runtime.images_file` | 本機 immutable image lock；恰有 `postgres`、`app` 兩個欄位 |
| `runtime.work_dir` | 與來源備份完全分離的私有 Linux 目錄；比對含 symlink 解析後的關係 |
| `runtime.timeout` | `1s`–`1h`，整數加 `s`、`m` 或 `h`；不可與 CLI `--timeout` 混用 |
| `checks` | 四個固定 ID 各出現一次，且 `required: true` |
| `report.formats` | `json`、`html` 各一次 |

四個檢查為 `sql-documents`、`database-files`、`login-search-download`、`external-connectivity`。此版使用模板內既有檢查，不能提交 `query`、`command` 或其他尚未有執行支援的欄位。報告格式也不能以省略格式的方式與執行行為脫節。

所有相對路徑都相對於傳入設定檔所在目錄，與呼叫 CLI 的 cwd 無關。路徑不展開 `$VAR`、`${VAR}` 或 `~`；不接受 URL、Windows drive path 或控制字元。設定不支援明文密碼／環境變數；演練密碼由 runner 產生，因此 plan 不需要讀取或解析秘密。

未知欄位、重複 key、多份 YAML document、anchor／alias／merge、自訂 tag、null、不支援的純量型別、超過 64 KiB 或深度／節點上限都拒絕。可定位的 schema 約束與 YAML 節點錯誤包含行列位置；其他錯誤以分類訊息回報，原始輸入值不直接拼入錯誤。設定 hash 是正規化宣告內容的 SHA-256，註解不影響 hash；plan 另列解析後的實際來源與 workspace。

## Manifest 與來源映射

| 設定角色 | 備份包內來源 | 演練目標 |
|---|---|---|
| `database` | `database.dump` | 新 PostgreSQL `documents` DB／新 database volume |
| `uploads` | `uploads.tar` | 新 uploads volume 的 `/uploads` |
| `app_config` | `app-config.sanitized.json` | 資訊紀錄；不是命令或可執行設定 |

這是固定模板的角色映射，不是任意 host 路徑轉掛載。缺少角色、重複／錯誤來源、越界名稱、額外角色或不支援的目標都拒絕。來源包恰有上述三份檔案及 `manifest.json`；額外檔案也拒絕。

Manifest 必須有完整 v1 欄位、PostgreSQL major 17、`plpgsql` extension、合法時間區間、immutable images、附件數量和完整檔案 inventory。其 JSON 不接受重複 key、缺欄位、unknown field、大小寫別名或 null；檔案大小、SHA-256、custom dump magic、tar 路徑／類型／展開限制與數量皆驗證。映像必須與使用者信任的本機 image lock 一致。

來源、設定與 image lock 使用 bounded regular-file 讀取；拒絕 symlink、FIFO 等特殊檔案，避免讀取卡住。讀取前後核對檔案身分、大小與修改時間。檔案 hash 不證明來源可信，也不能找出備份製作時原本就遺漏的附件；應用驗證仍由 run 負責。

## 命令行為與 exit code

| 命令 | 行為 | 結果 |
|---|---|---|
| `plan --config FILE` | 離線驗證設定、manifest、來源映射與 image lock，輸出 JSON 資源／步驟／檢查範圍 | 有效為 0；`environment_checked: false`，不是 readiness 保證 |
| `doctor --config FILE --offline` | 執行相同離線驗證，runtime 明確 skipped | 有效為 0；`status: offline_valid`、`ready: false` |
| `doctor --config FILE` | 離線驗證加本機平台、Docker／Compose、空間、容量、映像、workspace 查核 | ready 為 0，not_ready 為 1 |
| `run --config FILE` | 重新建立 plan、執行 doctor，再進入 M1 還原流程 | 檢查與清理皆成功才為 0 |

設定語法／schema 或 CLI 參數錯誤為 exit 2；來源、manifest、環境或執行失敗為 exit 1。`--config` 不可混用舊的 `--bundle`、`--images`、`--work`、`--timeout` 等 override，避免 plan 與實際執行不同。M1 的舊指令仍可獨立使用；它們不會憑空取得設定 hash。

plan 完全不呼叫 Docker、不建立 workspace／lock／容器、不執行備份中的命令。doctor 的 Docker 呼叫限於 version、info、compose version、image inspect；不 pull、不 build、不建立資源。一般 doctor 要求 Linux/amd64、Docker API >=1.44、Compose v2、至少 2 CPU／2 GiB engine RAM，以及 workspace 與 Docker 儲存各至少 1 GiB 可用空間；這些是基本門檻，不是效能保證。

`run --config` 在 staging 後核對此次規劃的 manifest SHA-256。若規劃後 manifest 被替換，即使新 manifest 本身合法，也在 restoring 前失敗並清理。報告記錄 `config_hash`；不把 plan 當成永不過期的授權或備份快照。再次獨立執行 run 會重新讀取設定與來源。

## 驗收

```sh
go test -race ./...
go vet ./...
python3 tests/integration/m2.py
python3 tests/integration/m1.py
```

整合測試包含真正製作備份與設定驅動的還原，也以禁止 Docker 的 shim 證明離線 plan 不使用 Docker。來源 hash、Docker 資源清單及 workspace 存在性在前後比對。結果見 [M2 驗收紀錄](M2_ACCEPTANCE.zh-TW.md)。

依賴固定為 `go.yaml.in/yaml/v3 v3.0.4` 與 `github.com/santhosh-tekuri/jsonschema/v5 v5.3.1`，雜湊保存在 go.sum。參考：[YAML v3](https://pkg.go.dev/go.yaml.in/yaml/v3)、[JSON Schema 驗證器](https://pkg.go.dev/github.com/santhosh-tekuri/jsonschema/v5@v5.3.1)、[JSON Schema 2020-12](https://json-schema.org/draft/2020-12)。
