# Compose Recovery Lab

Docker Compose 應用的自動還原演練專案。

目標是使用既有備份，在乾淨測試環境恢復資料庫、附件與網站，驗證指定的使用流程，輸出可追溯報告並清理演練資源。

## 目前狀態

**M1 實作中。** 已加入文件網站 API fixture、合成資料初始化、Compose 設定與 HTTP/檔案單元測試；尚無完整還原 CLI，Docker/PostgreSQL 整合尚未驗收。使用方式見 [文件網站](examples/document-app/README.md)。

- [詳細計畫書（繁體中文）](docs/OPERATIONS.zh-TW.md)
- [開發與 commit 規範](AGENTS.md)
- [里程碑紀錄](docs/M3_M6_ACCEPTANCE.zh-TW.md)

## 第一版目標

- Linux、Docker Compose、PostgreSQL 與一般附件目錄。
- 從本機備份包重建一個完整應用。
- SQL、檔案關聯、HTTP 與端到端驗證。
- 持久化狀態、程序中斷回收、明確的資源所有權。
- JSON/HTML 報告，清楚列出通過、失敗與未涵蓋的範圍。

## 開發原則

每完成一個可驗收部分，先檢查、再 commit。秘密、正式備份、資料庫 dump、執行日誌及演練產物不得提交。

下一步為 M1：建立文件網站示範、製作合成備份，在臨時環境恢復並成功下載文件。完整規格與估時見計畫書。
