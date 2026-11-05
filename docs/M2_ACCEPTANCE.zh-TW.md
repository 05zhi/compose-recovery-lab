# M2 驗收紀錄

- 日期：2026-11-04（Asia/Taipei）。
- 範圍：版本化設定 schema、manifest／來源映射驗證、只讀 doctor／plan、設定驅動還原與負向測試。
- 結論：固定 `document-app-v1` 契約的 M2 通過；M3–M6 不在完成範圍。
- 環境沿用 [M1 實測環境](ENVIRONMENT.zh-TW.md)，新增依賴固定於 go.mod／go.sum。

## 程式與靜態檢查

- `go test -race ./...`：通過。
- `go vet ./...`：通過。
- 配置、planner 與來源負向測試：版本／型別、未知欄位、重複 key、多文件、anchor、merge、null、逾時範圍、環境展開、缺少／重複／可略過檢查、source mapping、manifest 時間／數量／大小、symlink、FIFO、額外來源檔案、image lock 不符等均拒絕。
- doctor 單元測試：正常與 offline、Docker 不可用、API 過舊、Compose v1、RAM 不足、映像缺失、錯誤 CPU 架構、workspace 是檔案或非私有目錄等。
- 發布的 YAML 範例由同一個 CLI schema parser 驗證，避免文件與程式規則分離。

doctor 環境分支的單元測試使用查詢替身；下面的備份、環境就緒、還原及清理則是真實 Docker 驗收，不把 mock 當成整合證據。

## M2 真實 CLI 驗收：28 個情境

| 類別 | 實際案例 | 預期／觀察 |
|---|---|---|
| 基準來源 | 真實 PostgreSQL custom dump 備份 | exit 0，來源資源清理完成 |
| 離線規劃 | Docker shim 禁止所有呼叫 | plan exit 0，shim 未被呼叫、workspace 未建立 |
| 離線 doctor | `--offline` | exit 0、offline_valid、ready=false，runtime skipped |
| Docker 不可用 | 一般 doctor 經失敗 shim | exit 1、ready=false，不建立資源 |
| 真實 doctor | 本機 Docker／Compose／images／space | exit 0、ready=true |
| 不支援設定（12 項） | schema version、host network、privileged、host bind、external volume、command、secret、環境展開、映射越界、缺映射角色、optional check、自訂 query | exit 2；輸出不含測試秘密值 |
| CLI 衝突 | `--config` 混用 `--bundle` | exit 2 |
| YAML 結構（3 項） | 重複 key、多文件、anchor | exit 2 |
| Manifest（3 項） | DB major、extension、image 不符 | exit 1 |
| 路徑隔離 | workspace 經 symlink 指回來源內 | exit 1 |
| 設定驅動還原 | `run --config` | 四項必要檢查 passed，cleanup complete |
| 規劃後來源變動 | doctor 期間將 manifest 換成另一個合法內容 | exit 1，restoring 未開始、cleanup complete |
| 重複規劃 | 還原完成後再 plan | exit 0 |

所有命令從 `/` 呼叫、設定檔位於別處，確認相對路徑相對 config 所在目錄。plan／doctor 前後比對來源四個檔案的 SHA-256 及所有 Docker container／volume／network 清單；結果不變。成功還原報告的 `config_hash`、`backup_id` 與 plan 一致。

規劃後變動測試在 doctor 的 image inspect 階段注入合法 manifest 替換；runner 的 staging 後 SHA-256 綁定正確拒絕，沒有執行 restore。這不是只驗證損壞 JSON 的負向測試。

## 回歸與證據

另重跑 M1 的 15 個真實 Docker 故障／清理情境，完整、缺件、錯件、hash 損壞、tar 越界、restore failure、備份失敗、SIGTERM、SIGKILL 明確清理、cleanup failure／retry 與外部 sentinel 均符合預期。最後查詢 CRL labels，沒有容器、network 或 volume 殘留。

持久驗收目錄：

- WSL `./artifacts/crl-m2-acceptance-final/`：28 項 M2 summary、plan、doctor、完整備份及 run 報告。
- WSL `./artifacts/crl-m2-m1-regression-final/`：M1 回歸的來源包、summary 及各次報告。
- 本機 repo `reports/m2/`：可開啟的 plan、doctor、summary、成功還原及 manifest 變動拒絕報告複本；依 gitignore 不提交產物。

測試腳本可用 `--output NEW_DIRECTORY` 指定新目錄；M2 預設改存 Linux 使用者家目錄下的私有 acceptance 路徑，避免 WSL 重啟清理 `/tmp` 後證據遺失。

## 已完成的 commit 單位

| Commit | 內容 |
|---|---|
| `685c4f3` | 嵌入式 JSON Schema 與嚴格 YAML 設定驗證 |
| `853f473` | 嚴格 manifest JSON、bounded no-follow 來源讀取 |
| `708fe43` | 唯讀 doctor／plan、來源映射、run --config |
| `4595bba` | M2 離線純度與真實 Docker 整合測試 |
| `ff2cbc2` | 不相容引擎與不安全 workspace 拒絕 |
| `65926dd` | 規劃後 manifest 變動與發布範例驗證 |
| `388c958` | 在 WSL 持久保存驗收證據 |

M2 仍只接受固定模板及其三個來源角色，不支援任意來源改名、host mount、自訂 SQL／command 或秘密注入。SQLite、自動重試、通用 checker、第二模板與完整多階段崩潰矩陣留待後續里程碑。詳見 [操作手冊](M2_RUNBOOK.zh-TW.md) 與 [ADR 0003](adr/0003-versioned-config-and-offline-plans.md)。
