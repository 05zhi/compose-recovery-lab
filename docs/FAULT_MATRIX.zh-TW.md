# 故障矩陣與驗收證據

以下對照既有的合成資料驗收。情境通過代表實際行為符合預期，因此包含預期被拒絕或驗證失敗的演練。原始報告由維護者保留，未發布。

| 案例 | 套件與情境 | 最近的已記錄證據 |
|---|---|---|
| 完整恢復 | M6 兩模板 `complete`；SQL、附件與瀏覽器流程 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 損壞備份 | M1 `corrupt-hash` 在還原前拒絕，`restore-error` 驗證已更新雜湊但無法還原的 dump | [十套件結果](M3_M6_ACCEPTANCE.zh-TW.md#可重現驗收)，`82a7396` |
| 空資料庫 | M6 兩模板 `empty-database`，還原後移除必要業務列，驗證不得為 passed | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 缺附件 | M6 兩模板 `missing-attachment`，以合法 bundle 觸發資料列與附件比對失敗 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 錯附件 | M6 兩模板 `wrong-attachment`，改動檔案後更新 manifest；M1 另斷言附件檢查失敗 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 權限錯誤 | M6 兩模板 `unreadable-file`，讓應用無法讀取合成附件，斷言附件檢查失敗 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 版本不符 | M6 兩模板 `version-blocked`，把 bundle 的 PostgreSQL major 改為不支援的版本，下游檢查全部略過 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 啟動失敗 | M6 兩模板 `startup-failure`，停止應用容器並驗證失敗與清理；Diagnostics 另驗證遮蔽後的 DB 日誌 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)、[十套件結果](M3_M6_ACCEPTANCE.zh-TW.md#可重現驗收)，`c944873`／`82a7396` |
| 程序中斷 | M3 兩模板六個階段 SIGKILL 後 recover；M6 `create-journal-gap` 覆蓋 Docker 建立後、journal 更新前的中斷 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 清理失敗 | M1 `cleanup-failure`、`cleanup-retry`，阻斷 Docker 移除命令後核對真實殘留與重試 | [故障與隔離證據](M3_M6_ACCEPTANCE.zh-TW.md#故障與隔離證據)，`82a7396` |
| 名稱碰撞 | M1 `foreign-resource-preserved`，建立相似名稱的外部 sentinel volume，比對清理前後的 Docker inspect | [十套件結果](M3_M6_ACCEPTANCE.zh-TW.md#可重現驗收)，`82a7396` |
| 越界路徑 | M1 `tar-traversal` 擋下惡意 archive 路徑；M6 兩模板 `db-path-escape` 檢查資料列引用 | [十套件結果](M3_M6_ACCEPTANCE.zh-TW.md#可重現驗收)、[修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`82a7396`／`c944873` |
| 對外副作用 | M1 成功演練確認主機能連指定 TCP 端點，應用所在的內部網路將該連線阻擋；M5 通知只用 loopback | [故障與隔離證據](M3_M6_ACCEPTANCE.zh-TW.md#故障與隔離證據)，`82a7396` |
| 必要測試略過 | M6 兩模板 `required-skipped`，令真實容器流程的必要探針無結果，整體不得通過 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |
| 重複演練 | M6 `repeat` 與兩模板長批次各 20 次完整還原，每次重建資源並核對清理 | [修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收)，`c944873` |

## P0 功能對照

| 要求 | 驗證狀態 | 證據或待補範圍 |
|---|---|---|
| Linux amd64、Docker Engine、Compose v2 | 部分驗證 | 已記錄 Ubuntu 24.04 WSL2 的版本；待補 Debian 13 與冷映像結果。[環境紀錄](ENVIRONMENT.zh-TW.md) |
| 在乾淨 Linux 測試環境重現 | 部分驗證 | 已在同一 WSL 主機用全新 HOME 驗證套件；待補新發行版冷映像，獨立 Linux VM 未驗證。[封裝與展示](M3_M6_ACCEPTANCE.zh-TW.md#封裝與展示) |
| 單一執行器與依序排程 | 已驗證 | M3 的帳號鎖與 attempt 歷史、M5 的依序排程。[驗收](M3_M6_ACCEPTANCE.zh-TW.md#可重現驗收) |
| PostgreSQL 邏輯備份 | 已驗證 | M1、M6 固定 PostgreSQL 17 與 custom-format dump；跨 major 恢復不在支援範圍。 |
| 附件目錄與受限服務拓樸 | 已驗證 | 文件與庫存模板、附件 tar、Docker inspect 驗證內部網路與服務限制。[隔離證據](M3_M6_ACCEPTANCE.zh-TW.md#故障與隔離證據) |
| 本機備份包與離線 manifest 核對 | 已驗證 | M2 的 schema、來源映射、唯讀預檢與離線 plan；M1 的損壞備份拒絕。 |
| CLI、JSON／HTML 報告與 SQLite 歷史 | 已驗證 | M5 查詢歷史與從 SQLite 再生 HTML，M1／M6 真實演練報告。 |
| SQL、附件與關聯、HTTP、應用 E2E | 已驗證 | M4 檢查類型與界線，兩模板的 Chromium 實際登入、搜尋與下載。[修正驗收](BROWSER_INCIDENT.zh-TW.md#修正驗收) |
| 取消、逾時、清理與中斷回收 | 已驗證 | M1 取消、清理重試；M3 六階段 runner 中斷；M4 檢查逾時。整個 WSL 與 Docker daemon 同時中斷另待驗收。 |
| 文件網站與第二個不同結構的模板 | 已驗證 | M6 雙模板，包含庫存彙總 CSV 與巢狀附件。[驗收](M3_M6_ACCEPTANCE.zh-TW.md#可重現驗收) |

真人獨立重現仍待回饋。以上對照採用既有整合證據，未新增或重複執行矩陣測試。
