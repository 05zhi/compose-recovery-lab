# ADR 0003：版本化設定與不具副作用的規劃

- 日期：2026-11-04
- 狀態：接受

以一份嵌入式 JSON Schema 2020-12 同時提供編輯器提示與 CLI 驗證。YAML 在 schema 驗證前限制為無 alias／merge／自訂 tag 的單一有界文件，避免型別強制轉換與不透明的繼承；錯誤不輸出原始值。解析器不執行命令、不讀取秘密或展開環境變數。

M2 保持 `document-app-v1` 的固定來源角色與四項必要檢查。草案中的自訂 SQL 與任意 checker 欄位在 M4 有實際執行支援前明確拒絕。相同理由使 host network、privileged、devices、host bind、external resource 等 Compose 欄位不能出現在設定中。這是明確限制，不是自動轉換任意 Compose。

planner 僅進行本機有界檔案讀取，並產生描述性的資源與來源映射；不建立工作目錄，也不查詢 Docker。doctor 在同一契約上加唯讀環境查核。離線 doctor 的有效結果是 `offline_valid`、`ready=false`，避免將未檢查的 runtime 視為通過。

`run --config` 重用 plan 和 doctor，禁止混用舊 CLI overrides。規劃時綁定原始 manifest SHA-256，staging 後再次核對，避免在同一次執行中悄悄換成另一份合法備份；設定 hash 則保存到報告。獨立 plan 不是鎖定未來來源的交易，下一次 run 仍重新驗證。

Manifest 與 image lock 採嚴格 JSON：拒絕重複、缺漏、unknown、null 與非明確型別。來源檔案以 Linux nonblocking／no-follow 開啟後再次核對身分，避免 FIFO 阻塞或檔案替換。來源與 workspace 在 symlink 解析後必須分離。

M3 的 SQLite 交易狀態與自動重試、M4 的通用檢查、M6 的第二模板仍不在本次完成範圍。
