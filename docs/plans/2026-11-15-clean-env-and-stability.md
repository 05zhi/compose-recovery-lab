---
status: in-progress  # draft | ready | in-progress | done | blocked
planner: claude
executor: codex
branch: main
created: 2026-11-15
---

# Compose Recovery Lab：乾淨環境、其他發行版、主機崩潰與長時間穩定性驗收

## 目標

M1–M5 已驗收，M6 的工程部分也已通過。`docs/M3_M6_ACCEPTANCE.zh-TW.md` 與 README 列出的未驗證範圍，有幾項不需要真人就能補上證據：

- 完整冷映像／乾淨環境：目前只在已有映像快取的同一個 WSL Ubuntu 驗證。
- 其他 Linux 發行版：只驗證過 Ubuntu 24.04。
- 整機層級中斷：只測過 runner 程序被 SIGKILL，沒測過 Docker daemon 與 runner 一起消失。
- 長期穩定性：瀏覽器啟動競爭修正後跑過 40 次完整還原，間歇性失敗的歷史紀錄仍在。

本計畫補上這四項，並整理一份對照私人計畫書測試矩陣的追蹤表，以及一份與現有工具的技術能力對照。真人試用、需求訪談、另一位使用者的獨立重現仍需要真人，不在本計畫內。

## 範圍

- 做：
  1. 提交搬遷路徑修正，在主 WSL 環境跑基準。
  2. 故障矩陣追蹤表（私人計畫書 §11 的 15 個案例 → 測試與證據），只補缺的。
  3. 在全新 WSL Ubuntu 24.04 發行版，從零依 README 安裝並跑完整驗收（冷映像）。
  4. 在全新 WSL Debian 13 發行版重複一次（其他發行版）。
  5. 在乾淨發行版中，於六個主要階段強制終止整個 Linux 環境（含 Docker daemon），驗證重啟後的 recover。
  6. 長時間穩定性：兩模板交替共 100 次完整還原。
  7. 以同一批故障備份，和 `pg_restore`、manifest 雜湊檢查、restic `check --read-data` 做技術能力對照。
  8. 文件與履歷句總整理。
- 不做：
  - 真人試用、需求訪談、聯絡外部人員、填寫試用回饋。
  - P1 範圍：restic／S3 備份來源、第二種資料庫、管理介面。
  - 支援任意 Compose 專案、正式環境還原、使用正式資料。
  - 建立 GitHub release、公開發布、對外宣傳（這些需使用者另外決定）。
  - 實體斷電或檔案系統損毀測試。WSL 強制終止只模擬「整個 Linux 環境與 Docker daemon 一起消失」，不等於實體斷電，文件必須這樣寫。
  - 為了讓測試通過而加入自動重試、放寬檢查或調高逾時。若必須調整資源預算，原始失敗證據保留，並照既有做法寫「不宣稱已確診唯一根因」。

## 背景與現況

- **工作路徑**：Windows `C:\Andy\dev\Projects\standalone\compose-recovery-lab`，WSL 內為 `/mnt/c/Andy/dev/Projects/standalone/compose-recovery-lab`。舊路徑 `D:\Codex\Projects\...` 已不使用。
- **未提交的搬遷變更**：`AGENTS.md` 與 `docs/plans/README.md` 各有一行，把 `D:\Codex\Projects\...` 改成 `C:\Andy\dev\Projects\...`。這是使用者搬遷時留下的，步驟 0 提交（見檢查條件）。
- **主驗收環境**：既有 WSL 發行版 `Ubuntu`（24.04.2），以 `wsl -d Ubuntu -u root -- bash` 進入；Docker Engine 29.1.3、Compose 2.40.3、Go 1.22.2，版本見 `docs/ENVIRONMENT.zh-TW.md`。Docker 只用本機 Unix socket，一般使用者沒有加入 docker 群組。WSL 版本 2.4.13。
- **這個 Docker daemon 也被其他專案使用**（pdf-proofreading-workbench 的容器驗收可能同時進行）。清理只能用本工具的 run ID、resource ID 與標籤，**禁止任何全域 prune**。
- **原始計畫書**是私人文件，不在 repo：`C:\Andy\dev\Projects\others\crl-rest\private-planning-20261105\PROJECT_PLAN.zh-TW.md`。可以讀，不可提交或整段複製進 repo。§3.1 P0、§11 測試矩陣、§14 展示是本計畫的依據。
- **已驗收的完整入口**：`python3 scripts/acceptance.py --output "$HOME/<新目錄>"` 跑十個套件（M2、M1 兩模板、M6 兩模板、M3 兩模板、M4、M5、Diagnostics），支援 `--resume`。結果目錄放在 `$HOME`，不放 repo。
- **間歇性失敗的歷史**：見 `docs/BROWSER_INCIDENT.zh-TW.md`。glibc 2.41 基底修正後通過 40 次完整還原／840 次瀏覽器流程。舊的兩筆失敗不能逐筆證明同因，紀錄不可改。
- **磁碟**：C: 只剩約 65 GB。兩個新發行版加映像預估各 6–10 GB（估計）。WSL 發行版的磁碟檔放在 `C:\Andy\wsl\<名稱>\`（repo 之外）。開始步驟 3 前剩餘空間必須 ≥ 35 GB；任何時候低於 20 GB 就停止。

## 會改的檔案

- `AGENTS.md`、`docs/plans/README.md`：步驟 0。
- `docs/FAULT_MATRIX.zh-TW.md`（新）、必要時 `tests/integration/*.py`：步驟 1。
- `docs/CLEAN_ENVIRONMENT.zh-TW.md`（新）、`docs/ENVIRONMENT.zh-TW.md`、README 與 `docs/OPERATIONS.zh-TW.md`（只修步驟 2–3 發現的文件錯誤）：步驟 2–3。
- `scripts/host_crash.py`（新，在 Windows 端執行）、`docs/HOST_CRASH.zh-TW.md`（新）：步驟 4。
- `scripts/soak.py`（新，或擴充 `tests/integration/stability.py`）、`docs/STABILITY.zh-TW.md`（新）：步驟 5。
- `scripts/compare_tools.py`（新）、`docs/TOOL_COMPARISON.zh-TW.md`（新）：步驟 6。
- `README.md`、`docs/M3_M6_ACCEPTANCE.zh-TW.md`：每步更新與步驟 7。

## 步驟

每一步是一個可驗收部分：完成後跑該步檢查，更新驗收文件，明確 stage，`git diff --cached --check`，commit，push，確認遠端 SHA。commit 與 push 分開回報（本專案 AGENTS.md 規則）。工時為估計，含機器執行時間。

### 0. 狀態、搬遷提交與基準（約 1–2 h）

1. 本檔 `status` 改為 `in-progress`。`git status`、`git fetch`。
2. 看 `git diff`：若 `AGENTS.md` 與 `docs/plans/README.md` 都只是把 `D:\Codex\Projects` 換成 `C:\Andy\dev\Projects`，才提交；有其他內容就停止並改為 blocked。
3. 在主 WSL `Ubuntu`（root）進入新路徑：
   ```sh
   go build -buildvcs=false -o bin/crl ./cmd/crl
   go test -race ./...
   go vet ./...
   python3 -m unittest discover -s examples/document-app -p test_app.py
   ```
   再依 README「使用步驟導覽」跑一次完整文件備份還原與缺附件情境，確認結果分別為 passed 與 failed、cleanup complete、資源零殘留。
   - 驗收：全部符合預期；若新路徑造成問題（例如 `/mnt/c` 權限或路徑長度），記錄並修正文件或程式。
4. commit：`docs: update paths after moving to standalone folder`

### 1. 故障矩陣追蹤表（約 2–3 h）

1. 新增 `docs/FAULT_MATRIX.zh-TW.md`：把私人計畫書 §11 的 15 個案例（完整恢復、損壞備份、空資料庫、缺附件、錯附件、權限錯誤、版本不符、啟動失敗、程序中斷、清理失敗、名稱碰撞、越界路徑、對外副作用、必要測試略過、重複演練）逐列對應到：套件、測試名稱或情境名稱、最近一次通過的證據（驗收文件段落與 commit）。用自己的話描述案例，不要複製私人計畫書原文。
2. 再對照 §3.1 P0 每一條，標明已驗證、部分驗證（寫缺什麼）或未驗證。
3. 只為「缺」的案例補整合測試（必須建立真實容器，不能只用 mock），通過後一起提交。
- 驗收：15 列都有對應或「不適用＋理由」；P0 對照完整；新增測試通過。
- commit：`docs: trace fault matrix cases to acceptance evidence`（有新測試用 `test:`）

### 2. 全新 WSL Ubuntu 24.04：冷映像完整驗收（約 4–6 h）

1. 檢查 C: 剩餘空間 ≥ 35 GB。
2. 建立發行版 `crl-clean-ubuntu`，擇一並記錄：
   - `wsl --install -d Ubuntu-24.04 --name crl-clean-ubuntu --location C:\Andy\wsl\crl-clean-ubuntu --no-launch`（先用 `wsl --help` 確認此版 WSL 支援這些參數）；或
   - 從 `https://cloud-images.ubuntu.com/wsl/` 下載 noble 的 WSL rootfs，**核對官方 SHA256SUMS**，再 `wsl --import crl-clean-ubuntu C:\Andy\wsl\crl-clean-ubuntu <檔案>`。
3. 在新發行版內：啟用 systemd（`/etc/wsl.conf`），用 Ubuntu 套件安裝 `golang-go docker.io docker-compose-v2 python3 git gcc`（與 `docs/ENVIRONMENT.zh-TW.md` 相同方式），記錄實際版本。此時 Docker 沒有任何映像快取，這就是「冷映像」條件。
4. **完全照 README 的指令**從頭做：`git clone`（若 GitHub 需要認證而失敗，改從 `/mnt/c/...` 本機路徑 clone 同一個 commit，並記錄這個偏差）、`go build`、`python3 scripts/prepare-images.py`、成功與缺附件兩個情境、`history`。每一個與 README 不一致、缺漏或需要猜的地方都記錄為文件問題。
5. 跑完整驗收：`python3 scripts/acceptance.py --output "$HOME/crl-acceptance-clean-ubuntu"`。失敗時先保留證據，再依既有 `--resume` 流程處理；不要把重跑結果說成首次全綠。
6. 核對演練資源零殘留（只查本工具標籤的 containers／networks／volumes）。
7. 新增 `docs/CLEAN_ENVIRONMENT.zh-TW.md`：發行版來源與 SHA-256、所有套件版本、映像 digest 與 ID、各套件結果、耗時、README 問題清單與修正。修正 README／OPERATIONS 的文件問題。
- 驗收：十個套件結果完整記錄（通過或失敗都寫）；文件問題已修或列為待辦。
- 文件中明寫：這是同一台實體機上的新 WSL 發行版與冷映像，不是另一台 VM，也不是另一位使用者。
- 新發行版保留不刪，供步驟 4 使用；整份計畫結束後由使用者決定是否 `wsl --unregister`。
- commit：`test: verify install and full acceptance on a fresh Ubuntu WSL distro`

### 3. 全新 WSL Debian 13：其他發行版驗收（約 4–6 h）

1. 檢查剩餘空間。建立 `crl-clean-debian`，擇一並記錄：
   - `wsl --install -d Debian --name crl-clean-debian --location C:\Andy\wsl\crl-clean-debian --no-launch`；或
   - 在主 `Ubuntu` 的 Docker 中以**固定 digest** 的官方 `debian:trixie` 映像建立容器，`docker export` 成 rootfs，再 `wsl --import`。匯出完刪除這個暫時容器（只刪自己建立的那一個）。
2. 用 Debian 套件安裝相同工具，記錄版本。Go、glibc、Docker 版本與 Ubuntu 不同是預期的，正是本步要驗證的。
3. 重複步驟 2 的第 4–6 項，結果目錄 `$HOME/crl-acceptance-clean-debian`。
4. 若出現只在 Debian 失敗的問題：查明原因。屬於本工具的 bug 就修並附測試，兩個發行版都重跑受影響套件；屬於環境差異就寫進支援範圍與限制，不硬改程式。
5. 更新 `docs/CLEAN_ENVIRONMENT.zh-TW.md` 與 README 的「已驗證環境」。
- commit：`test: verify full acceptance on a fresh Debian 13 WSL distro`

### 4. 主機層級中斷：Linux 環境與 Docker daemon 一起終止（約 4–6 h）

在 `crl-clean-ubuntu` 執行，**不要對主 `Ubuntu` 發行版做這件事**（它可能正在跑其他專案的工作）。

1. 新增 `scripts/host_crash.py`（Windows 端 Python 執行）：
   - 在 `crl-clean-ubuntu` 啟動一次完整文件模板演練。
   - 監看該次 attempt 的階段（用 `bin/crl status` 或 journal，不要靠固定 sleep），到達目標階段後立即從 Windows 執行 `wsl --terminate crl-clean-ubuntu`。
   - 重新進入發行版，等 Docker 服務就緒，執行 `bin/crl recover`，再查狀態、歷史與標籤資源。
   - 最後以同一 logical run 跑一個全新 attempt，必須 passed。
2. 涵蓋與 M3 SIGKILL 相同的六個主要階段；兩個模板都做。每個情境重複 2 次。
3. 每個情境記錄：終止時階段、重啟後 Docker 中殘留的容器／網路／volume、recover 結果、前一個 attempt 的最終狀態（不得為 passed）、清理結果、新 attempt 結果。
4. 若 Docker 重啟後有 recover 處理不了的狀態（例如 daemon 留下的半建立資源），屬於工具缺陷就修並附測試；屬於 Docker 本身行為就記錄限制。
5. 新增 `docs/HOST_CRASH.zh-TW.md`，第一段就寫明：這是 WSL 發行版被強制終止，模擬整個 Linux 環境與 Docker daemon 同時消失；不等於實體斷電，不涵蓋檔案系統損毀或磁碟寫入順序問題。
- 驗收：24 次情境（6 階段 × 2 模板 × 2 次）全部有紀錄；沒有任何被中斷的 attempt 被標為 passed；最終零殘留。
- commit：`test: recover after terminating the whole WSL environment at each phase`

### 5. 長時間穩定性：100 次完整還原（約 4–8 h，多為機器時間）

1. 新增 `scripts/soak.py`（或擴充 `tests/integration/stability.py`）：在主 `Ubuntu` 或 `crl-clean-ubuntu` 擇一（記錄是哪個），兩模板交替跑完整備份還原共 100 次，每次都含真實 Chromium 登入／搜尋／下載。
2. 每 10 次核對一次本工具標籤資源零殘留，並記錄 Docker 磁碟用量。
3. **不加自動重試**。任何一次失敗都完整保留證據、繼續跑完剩下的次數，最後彙總失敗次數、階段、類型。
4. 時間上限 8 小時；超時就停在當時次數，照實報告完成次數。
5. 新增 `docs/STABILITY.zh-TW.md`：環境、映像 ID、每次結果摘要、失敗清單與診斷、耗時分布、磁碟用量變化。若出現失敗，和 `docs/BROWSER_INCIDENT.zh-TW.md` 的已知模式比對，不能比對就寫「原因未確定」。
- 驗收：100 次（或時間到時的實際次數）全部有結果；結果無論好壞照實寫。
- commit：`test: run 100 alternating full restores and record stability`

### 6. 與現有工具的技術能力對照（約 3–4 h）

目的：用同一批故障備份，說明只驗證資料庫或備份完整性的做法會漏掉什麼。這是技術能力對照，不是產品優劣評比或使用者研究。

1. 用 `bin/crl backup` 產生四份文件模板備份：完整、缺附件（`--omit-attachment`）、錯附件、空資料庫（若既有選項或 fixture 支援；不支援就用 M6 套件已有的同類 fixture）。
2. 新增 `scripts/compare_tools.py`，對每份備份執行：
   - 本工具 `bin/crl run`。
   - manifest 雜湊檢查（只核對 bundle 自帶 manifest）。
   - `pg_restore` 還原到全新 PostgreSQL 17 容器（使用 `docs/ENVIRONMENT.zh-TW.md` 已固定的 digest），記錄 exit code 與表格列數。
   - restic：把 bundle 備份進一個暫時的本機 restic repo，執行 `restic check --read-data`（使用固定 digest 的官方 `restic/restic` 映像）。
   所有容器與 volume 用本次唯一標籤或名稱建立，結束只刪這些。
3. 新增 `docs/TOOL_COMPARISON.zh-TW.md`：4 份備份 × 4 種做法的結果表，以及每一格「它檢查什麼、沒檢查什麼」。明寫：restic 與 pg_restore 本來就不是為應用層驗證設計的，對照只說明檢查層次不同。
- 驗收：16 格都有實際執行結果與證據路徑；沒有推測值。
- commit：`docs: compare detection coverage with pg_restore, manifest hashes and restic`

### 7. 文件總整理與履歷句（約 1–2 h）

1. README「目前可用程度」：更新已驗證環境（兩個新發行版、冷映像）、主機層級中斷、100 次穩定性的實際結果，以及仍未驗證的範圍（實體斷電、檔案系統損毀、其他 CPU 架構、正式資料、真人試用）。
2. `docs/M3_M6_ACCEPTANCE.zh-TW.md` 新增一節，連到本計畫產出的文件。
3. 在驗收文件寫一句履歷用句子，**只填實測數字**。例如：「在 X 類故障案例與 Y 次主機層級中斷中驗證資料缺漏偵測與中斷回收；兩個 Linux 發行版的乾淨環境完成完整驗收；100 次連續還原 Z 次通過」。不寫任何使用者回饋或採用情況。
4. 列出使用者可以決定的後續事項：是否刪除兩個新 WSL 發行版、是否建立 GitHub release、是否開始招募試用者。
5. 本檔填寫「執行紀錄」，`status` 改為 `done`。
- commit：`docs: summarize clean-environment, host-crash and stability acceptance`

## 停止條件

遇到下列情況，停止目前步驟，`status` 改為 `blocked`，在執行紀錄寫明原因與需要的決定，commit 並 push 計畫檔：

- C: 剩餘空間低於 20 GB，或步驟 2 開始前低於 35 GB。
- 建立 WSL 發行版需要管理員權限、啟用 Windows 功能或變更系統安全設定。
- 需要把一般使用者加入 docker 群組、開啟 Docker TCP API 或放寬 socket 權限。
- 需要付費、登入第三方帳號或聯絡外部人員。
- 未提交檔案的內容與本計畫描述不符，或出現不是自己造成的新變更。
- 任何操作可能影響主 `Ubuntu` 發行版中其他專案的容器或資料。

## 給執行者的 prompt

> 執行 `docs/plans/2026-11-15-clean-env-and-stability.md`。依步驟實作，每完成一個可驗收部分就 commit 並 push。完成後填寫「執行紀錄」並把 status 改為 done；受阻時改為 blocked 並寫明需要的決定。

執行者需要特別注意：

1. 開始前依序讀 `C:\Andy\dev\Projects\AGENTS.md`、本專案 `AGENTS.md`、`README.md`、`docs/OPERATIONS.zh-TW.md`、`docs/M3_M6_ACCEPTANCE.zh-TW.md`、`docs/BROWSER_INCIDENT.zh-TW.md`、私人計畫書（只讀），以及本計畫。
2. 你是執行者，不是決策者。不要擴大支援範圍、不要加自動重試、不要調高逾時來讓測試通過。認為計畫有錯時，寫出理由並改為 blocked。
3. 嚴禁：`docker system prune` 或任何全域清理、刪除不是本次建立的容器／volume／網路／WSL 發行版、對主 `Ubuntu` 執行 `wsl --terminate`、提交 `.env`、備份、DB dump、日誌、報告、錄影或 `images.lock.json`、提交私人計畫書內容、force-push、amend 已推送 commit。
4. 每個結果都要有證據路徑；證據放 `$HOME` 下的新目錄，不放 repo。驗收文件只寫摘要與證據位置，沿用既有「維護者保留的本機驗收產物（未發布）」寫法。
5. 失敗、中斷、略過、清理失敗都不能寫成通過；重跑結果不能取代首次結果。
6. commit 與 push 分開回報；每一步都更新驗收文件。

## 執行紀錄

- 執行者／日期：Codex，2026-11-15 執行基準，2026-11-17 核對證據。
- 步驟 0：確認兩份搬遷差異都只更新共用規則路徑。Go build、race、vet、Python 9 項通過；完整文件還原 passed，缺附件還原 failed。四次備份／還原均清理完整，依 attempt 標籤核對零殘留。證據為既有 Ubuntu 的 `~/crl-relocation-baseline-20261115`，原始產物未發布。
- 偏離計畫之處：使用者提供的 `questions` 路徑沒有該檔，依同名且內容一致的本專案計畫接續。基準使用合成備份、獨立工作目錄及既有映像。
- 未完成或未驗證：步驟 1–7。
