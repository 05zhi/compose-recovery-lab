# 乾淨 WSL 環境驗收進度

2026-11-19 核對結果。目前受阻於 WSL 共用網路，完整驗收尚未完成。

## 已執行範圍

以 WSL 2.4.13 的 `--install --web-download --name --location --no-launch` 建立兩個全新發行版。systemd 已預設啟用，使用各發行版套件安裝 Go、Docker、Compose、Python、Git、GCC。Docker 僅經本機 Unix socket 存取。兩者都在映像數為零時開始，從公開 GitHub clone `d5283d3` 並完成 Go 建置。

| 環境 | 實際進度 |
|---|---|
| Ubuntu 24.04.5 amd64 | Go 1.22、Docker 29.1.3／API 1.52、Compose 2.40.3。冷快取映像準備成功，README 完整還原 passed、缺附件 failed，兩者 cleanup complete，history 可讀取。 |
| Debian 13.5 amd64 | Go 與工具安裝、空快取確認、clone、建置通過。Docker 26.1.5／API 1.45、Compose 2.26.1。兩次映像準備都在 PyPI 下載時 ReadTimeout，尚未進入演練。 |

這是在同一台實體機上的兩個新 WSL 發行版與冷映像條件下執行。獨立 VM 與另一位使用者的操作尚待驗證。

Ubuntu 的文件映像為 `sha256:7e8ed864dac6` 前綴，庫存映像為 `sha256:c9901063ee14` 前綴；完整 immutable ID 與建置日誌由維護者保留。PostgreSQL 與 Python 基底使用既有固定 digest。準備映像的實測耗時約 366 秒，完整還原約 53.35 秒，缺附件還原約 37.17 秒。這些數字來自本輪 README 演練。

## 首次結果與續跑

Ubuntu 完整入口共有 13 個套件。首次 M2 通過，M1 執行期間整個工作階段中斷，之後發現兩個退出的演練容器。執行 recover 後封存中斷的 M1 目錄，再使用 `--resume` 接續。

續跑的 M1 完整備份、完整還原、重複還原通過，隨後缺附件備份在 seeding 階段發生 service readiness timeout。報告為 inconclusive、cleanup complete。DB 與 app 均為 running，未記錄 OOM；應用診斷包含遮蔽後的 traceback，無法由這些資料判定例外內容。原始失敗及兩次 Debian 建置失敗均保留，未變更逾時設定。

## 阻礙與需要的決定

實測主 Ubuntu、乾淨 Ubuntu、乾淨 Debian 的 `/proc/1/ns/net` 都是 `net:[4026531840]`，三個 daemon 的預設 bridge 都宣告 `172.17.0.0/16`。這些發行版共用網路 namespace，並行的 Docker 網路與防火牆規則可能互相影響。就緒逾時與套件下載失敗的直接因果尚未取得封包或未遮蔽例外證據。

執行者先前將三個 daemon 視為可獨立並行，造成驗收環境互相干擾的風險。已停止新增測試，讓既有 CLI 完成清理。三個 daemon 按本工具 ownership label 查詢 containers、networks、volumes 均為零。

依計畫「任何操作可能影響主 Ubuntu 中其他專案」的停止條件，後續需要決定採用真正獨立的 VM，或先為新發行版建立隔離網路。24 次整個環境中斷測試必須等隔離方式確認後執行。兩個新發行版及各自的 daemon 保留，尚未移除或變更其網路設定。

100 次交替演練也已停止。兩次完整備份與還原通過，第三次備份完成後停止，所有五份實際操作報告 cleanup complete。此結果不足以完成穩定性驗收。

## 本機證據

原始產物為維護者保留的本機驗收產物（未發布）。Ubuntu 的步驟紀錄、原始與續跑日誌、suite-results、interrupted 目錄、shared-network-blocker，以及主 Ubuntu 的 soak session-interrupted 記錄可供後續追查。新腳本草稿留在忽略的 `tmp/`，尚未完成實際驗收。

## 2026-11-25：獨立 VM 接續

使用者選定獨立 VM 後，已使用既有 VirtualBox 7.0.10 建立兩個專用客體。兩者各有 6 GiB 記憶體、32 GiB 動態磁碟、獨立 Linux 核心與 NAT，SSH 僅經主機 loopback 轉接。SSH 與 cloud-init 已確認就緒，目前正在安裝驗收工具，尚未完成 VM 內的 Docker 驗收。

| 客體 | 映像來源與校驗 |
|---|---|
| Ubuntu 24.04 | 官方 noble cloud VMDK，SHA-256 `9a1e3959c9f4ad9d4752101fd4ff9a43191fb7d72e61fa20e033f9fd235ce794`，與官方 SHA256SUMS 相符。[來源](https://cloud-images.ubuntu.com/noble/current/) |
| Debian 13 | 官方 genericcloud amd64 tar.xz，SHA-512 `156ec11d792d5d051923f6a16eb9a25025a58f3f8e71ed1204f2862f40480cf8ee8e89cf5ea3633cc7e1fb04879473f876cafe8404a387e08546af659ac862c1`，與官方 SHA512SUMS 相符。[來源](https://cloud.debian.org/images/cloud/trixie/latest/) |

目前客體核心分別為 Ubuntu `6.8.0-147-generic` 與 Debian `6.12.117+deb13-cloud-amd64`。原先的 4 vCPU／預設計時設定在此 Windows Hyper-V 相容模式下無法穩定完成開機，改為單 vCPU。Debian 採 Hyper-V paravirtualization；Ubuntu 明確重現 IO-APIC timer kernel panic，改為 KVM paravirtualization、關閉客體 IO-APIC 並啟用 HPET 後完成開機。兩者使用 virtio 網卡，Debian genericcloud 在 Intel 模擬網卡時只有 loopback，改用 virtio 後取得 DHCP 位址。這些是客體硬體配置，演練容器的資源與逾時設定尚未更動。

VM 建立、首次開機與修正過程均保留本機紀錄。主機 Windows 的 Hyper-V 與 WSL 設定沿用既有狀態。
