# M3–M6 本機工程驗收

日期：2026-11-04。M3、M4、M5 已完成；M6 的兩模板、本機故障矩陣、量測、封裝與展示交付已通過。M6 的真人獨立試用仍待實際回饋，因此不宣稱完整 P0 或使用者驗收全部完成。

## 可重現驗收

在已準備映像的專用 Linux 測試環境執行：

```sh
go build -buildvcs=false -o bin/crl ./cmd/crl
go test -race ./...
go vet ./...
python3 -m unittest discover -s examples/document-app -p test_app.py
python3 scripts/acceptance.py --output "$HOME/crl-acceptance-new"
```

本次完整入口十個套件全部 exit 0，證據位於 WSL `./artifacts/crl-release-acceptance/`。`suite-results.json` 的時間包含套件等待互斥鎖，不可當作還原耗時。可開啟的報告複本在 repo `reports/final/`，不提交 Git。

| 套件 | 實際內容與結果 |
|---|---|
| M2 | 28 個設定／manifest／doctor／plan／CLI 情境通過 |
| M1 文件模板 | 15 個備份、還原、取消、清理故障及外部 sentinel 情境通過 |
| M1 庫存模板 | 相同 15 個生命週期情境通過 |
| M6 文件模板 | 13 個完整／重複、缺件、錯件、版本、空 DB、DB 越界、不可讀檔案、啟動、必要探針缺漏與 intent gap 情境通過 |
| M6 庫存模板 | 相同 13 個情境通過，包含庫存彙總 CSV 與六份巢狀附件 |
| M3 文件模板 | 六個主要階段 SIGKILL → recover，加上同 logical run 的全新 attempt 重試，全部通過 |
| M3 庫存模板 | 相同六階段與新 attempt 重試通過 |
| M4 | 11 個真實 SQL／檔案／關聯／HTTP、逾時、唯讀寫入拒絕、列數、stacked query、權限與提前失敗覆蓋情境通過 |
| M5 | 歷史／status、SQLite 重建 HTML、成功不通知、loopback 失敗 webhook、依序排程通過 |
| Diagnostics | 真實 DB 容器狀態與遮蔽後就緒日誌擷取通過 |

另有全部 Go race／vet 與 Python 九項 fixture 單元測試通過。沒有把 mock 結果算作上述容器驗收。

## 故障與隔離證據

- 真實 Docker inspect 核對 internal network、無 published ports／host mounts／privileged／devices、CPU／memory／PID 限制及應用唯讀 rootfs。
- 文件與庫存模板都核對單一外連端點；主機可連、演練容器不可連。這不是全面 egress 稽核或惡意程式沙箱。
- 在 Docker 已建立 DB、runner 尚未寫回 observed resource ID 的時差點殺死 runner；初始 journal 無 ID，恢復仍能依 intent／標籤對帳並清除。
- SQL assertion 失敗維持 failed；必要檢查未執行不算 passed；取消與中斷分別記錄 canceled／inconclusive。清理失敗即使驗證 passed 仍非零，重試清理後不覆寫先前驗證事實。
- 目前資源預算：DB 512 MiB／128 PIDs，應用 768 MiB／256 PIDs，各 1 CPU；應用 init 與 256 MiB 私有 tmpfs。dump／restore 單步至多 600 秒，其餘 Docker 命令 90 秒，設定總逾時與取消仍優先。
- 最終核對本工具 Docker containers／networks／volumes 零殘留。保留的合成備份、歷史、報告與錄影不屬於應刪除的演練資源。

初次效能測試曾出現一項無法細分原因的應用／瀏覽器失敗；提高受限資源預算及 init 後重測。另一次 1 GiB 還原達原本 90 秒上限；調整 bulk ceiling 後重測。原始失敗證據保留在 `./artifacts/crl-benchmark-final/` 與 `./artifacts/crl-benchmark-verified/`，未列入下表成功量測，不將資源調整宣稱為已確診唯一根因。

### 間歇性應用檢查失敗

完整回歸第一次執行到 M3 文件模板時，六階段崩潰回收通過，但隨後的新 attempt 出現一次 login-search-download 失敗，SQL、附件及 cleanup 均通過，容器沒有 OOM，未產生 browser.webm。原始報告與 suite-failure.json 保留於 `./artifacts/crl-release-acceptance/m3-document/`。

以暫時診斷 wrapper 只加入例外類型與 traceback 程式位置後，十二次完整重跑皆通過，未能重現根因。再用未修改的正式執行路徑重跑 M3 與後續套件通過。這是尚未確診的間歇性失敗，不能宣稱已修復或證明長期穩定；正式使用前需要持續試用及更長期觀察。失敗從未自動轉成通過。

`scripts/acceptance.py --output 原目錄 --resume` 可保留成功套件及原始失敗資料，用新目錄重跑失敗套件後繼續。最終 suite-results.json 是各套件最後一次結果，不代表首次執行全綠。

## 100 MiB／1 GiB 實測

資料為高度可壓縮的合成 PostgreSQL payload：每列 32 KiB、3200／32768 列，該欄位 TOAST 壓縮停用，dump 壓縮保留。邏輯資料大小不同於 dump 大小；這不是 1 GiB 附件、不可壓縮備份或大量 HTTP 下載測試。

暖輸入先讀取指定備份檔。冷輸入只逐檔使用 posix_fadvise 並以 mincore 確認執行前頁面不在記憶體；不清空主機 cache，兩者映像均已在本機。每組三次，CLI wall time 包含 plan／doctor、還原、檢查與清理，不含映像準備及製作來源備份。

| 邏輯 payload | 輸入 cache | 三次 wall time（秒） | 平均（秒） | dump bytes | 還原 DB bytes（第一輪） |
|---|---|---|---:|---:|---:|
| 100 MiB | 暖輸入 | 15.397 / 16.508 / 16.077 | 15.994 | 342,393 | 120,736,915 |
| 1024 MiB | 暖輸入 | 59.215 / 121.085 / 106.387 | 95.562 | 3,485,675 | 1,163,725,971 |
| 100 MiB | 冷輸入 | 15.759 / 16.068 / 16.168 | 15.999 | 342,393 | 120,736,915 |
| 1024 MiB | 冷輸入 | 32.530 / 68.447 / 53.578 | 51.518 | 3,485,675 | 1,163,725,971 |

十二次均通過全部應用檢查、payload 列數／總位元組數／第一筆內容斷言，cleanup=complete；沒有宣稱逐筆 hash 全部 benchmark payload。原始階段起訖與耗時見 `./artifacts/crl-benchmark-warm-final/summary.json`、`./artifacts/crl-benchmark-cold-final/summary.json`。冷輸入 replay 以 0.1 秒取樣工作目錄與 Docker 檔案系統用量差；它是受主機活動影響的觀察值，不是硬性 quota 或保證峰值。三次樣本及大幅時間變動不足以推論 RTO。

## 封裝與展示

- 套件驗收核對 SHA-256、路徑與權限（無 group/world write），確認沒有 dump、image lock、SQLite 或 reports；解壓後以全新 HOME／SQLite 執行 doctor、plan、完整還原與 history，全部通過。原始紀錄：`./artifacts/crl-package-install-check/summary.json`。這是在相同 Linux 主機與已信任的快取映像上測試，不能稱為另一台乾淨 VM 或另一位使用者的獨立驗證。
- 約 185 秒的實際報告導覽：`reports/final/recovery-walkthrough.webm`，Chromium 驗證長度 184.96 秒並檢查畫面。它是證據導覽，非模擬即時演練；個別 attempt 的 browser.webm 才是實際應用操作錄影。重製方式見 [展示說明](DEMO.zh-TW.md)。
- [操作／安裝手冊](OPERATIONS.zh-TW.md)、[架構圖](ARCHITECTURE.md)、[ADR](adr/0004-durable-adapters.md)、[獨立試用流程](TRIAL_GUIDE.zh-TW.md)。

## 尚未完成的外部驗證

尚無兩名真人獨立試用、3–5 位需求訪談或實際回饋修正；未聯絡外部人員。需要真實參與者後才能完成這部分 M6。沒有把自動化測試當作真人回饋。

已驗證範圍為這台 WSL2 Ubuntu 24.04／Linux amd64 與兩個合成模板；未驗證完整冷映像／冷 VM、整機斷電或檔案系統損毀、其他 Linux 發行版、正式資料與外部業務依賴。只支援受限本機 bundle、PostgreSQL 17 與已鎖定可信映像。上述邊界不因測試成功而擴大。


## 2026-11-05：間歇性應用檢查後續

後續已重現並修復 Chromium 啟動時 glibc 環境陣列讀寫競爭，新增原生訊號診斷、libc 根因回歸與長批次驗證。新映像通過 40 次完整還原／840 次瀏覽器流程及兩模板崩潰回收矩陣。當時兩筆歷史失敗因未保存例外，仍不能逐筆證明同因；原始失敗紀錄不變。[完整根因、修正與限制](BROWSER_INCIDENT.zh-TW.md)。
