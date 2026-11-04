# M1 驗收紀錄

- 日期：2026-11-04（Asia/Taipei）。
- 結論：固定 `document-app-v1` 的 M1 垂直切片通過；不代表 M2–M6 或完整 P0 驗收完成。
- 環境：WSL2 Ubuntu 24.04.2 x86-64、Go 1.22.2、Docker 29.1.3、Compose 2.40.3、PostgreSQL 17.6、Python 3.12.12。完整版本與 digest 見 [環境紀錄](ENVIRONMENT.zh-TW.md)。
- 核心 commit：`2c4ea14`、`00a0280`；整合矩陣：`42054a3`；報告與備份失敗處理：`6563b15`。

## 實際執行

```text
go test ./...                         PASS
go vet ./...                          PASS
go test -race ./...                   PASS
python3 -m unittest discover -s examples/document-app -v
                                     9 tests PASS
python3 tests/integration/m1.py       PASS（兩輪；第二輪含備份失敗恢復案例）
```

整合測試使用真實 Docker 容器、PostgreSQL custom dump、真實附件與 HTTP API；不是以 mock 代替還原。只有備份命令失敗及清理命令失敗使用 CLI shim 注入，底層建立及待清理資源仍是真實 Docker 資源。

## 第二輪觀察結果

| 案例 | 驗證結果 | 清理結果 | 階段耗時合計 |
|---|---|---|---:|
| 完整備份 | passed | complete | 25.575 s |
| 完整還原、10 份下載與 hash | passed | complete | 12.486 s |
| 同一備份再次獨立還原 | passed | complete | 12.525 s |
| 製作合法缺件備份 | passed（製作成功） | complete | 24.866 s |
| 缺附件還原 | failed | complete | 12.496 s |
| dump hash 損壞 | failed，未開始 restore | complete | 0.934 s |
| 附件錯內容、重算合法 manifest | failed | complete | 12.384 s |
| tar `../` 越界、重算合法 manifest | failed，未開始 restore | complete | 0.927 s |
| custom dump 格式錯誤、合法 hash | inconclusive；必要檢查 skipped | complete | 6.933 s |
| 停止來源後 pg_dump 失敗 | inconclusive；執行恢復來源服務；未發布完整包 | complete | 26.553 s |
| 觀察到容器後 SIGTERM | canceled | complete | 未彙總 |
| 觀察到容器後 SIGKILL，再明確 cleanup | inconclusive | complete | 未彙總 |
| 所有檢查成功但清理命令失敗 | passed，但 CLI 非零 | failed | 11.570 s |
| 清理重試 | 保留原本 passed | complete | 未彙總 |
| 相似名稱的非本次 sentinel volume | 未變動 | 測試自己回收 sentinel | 不適用 |

另以 `--timeout 3s` 測試總逾時：回傳非零、結果 canceled、cleanup complete。

缺附件案例具體觀察：`sql-documents=passed`、`database-files=failed`、`login-search-download=failed`、`external-connectivity=passed`。這證明 DB 恢復成功不等於附件／下載功能可用；不推論正式環境缺件的根因。

外部連線測試先確認 Linux 主機可連至 `1.1.1.1:443`，再確認演練內連線失敗。只代表該指定 TCP 端點的有限驗證。每個完成／故障案例核對該 run 的容器、network、volumes 無殘留；最後再查詢所有 CRL labels，結果亦為零。

清理失敗時取出當次隨機密碼，確認 JSON、HTML 與資源 journal 均不含該值；清理重試成功後移除私有 Compose 工作檔。單元測試另確認 HTML 轉義、必要檢查缺少／略過／重複不得通過，以及 tar 路徑與 symlink 拒絕。

## 證據及重現

- 完整第二輪證據保留在 WSL 的 `/tmp/crl-m1-acceptance-02/`，含每次報告與合成備份。
- 可直接開啟的 JSON／HTML 複本位於本機 repo 的 `reports/m1/`（Git 忽略），包含 `complete-restore` 與 `missing-attachment`。
- 操作指令與清理限制見 [M1 操作手冊](M1_RUNBOOK.zh-TW.md)。

上述耗時是本機、已快取映像、10 份小型合成文件的觀察值，包含各階段及清理，不含映像下載／建置。不是效能 benchmark，也不是 RTO 保證。未執行冷快取三次量測、100 MB／1 GB 資料集、第二模板或所有階段的強制中斷矩陣。

M1 留有明確限制：固定模板、備份來源為本工具的合成 fixture、密碼替換、owner/ACL 差異、JSON journal、手動 crash cleanup；不宣稱通用設定、完整 SQLite 歷史或自動續跑已完成。
