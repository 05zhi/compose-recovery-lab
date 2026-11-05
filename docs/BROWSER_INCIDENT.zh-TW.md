# 間歇性應用檢查失敗：根因與修正

日期：2026-11-05（Asia/Taipei）。範圍：本機 WSL2 Linux amd64、兩個合成模板。

## 根因證據

已重現的失敗是 Chromium 啟動期間，舊 glibc 2.36 的環境變數讀取遇到失效指標；頁面尚未建立，因此沒有影片。SQL、附件與資源清理仍通過。

1. 安全診斷保留錯誤分類與受信任程式行號，定位到 `browser_smoke.py` 的 `chromium.launch()`。原生日誌顯示 SIGSEGV／SI_KERNEL，當時沒有 OOM 或 PID 上限命中。
2. 獨立核心追蹤捕捉 `ThreadPoolForeg` → `exc_general_protection` → SIGSEGV。這是使用者態保護錯誤，並非 rseq 核心錯誤路徑。追蹤 instance 已移除；其中 `crl-trace-check` 是已處理的診斷自我檢查訊號，不計入失敗。
3. 同一映像再現時，RIP 對應 libc offset `0x3f14d`，即 `getenv+0x9d` 的 `cmp (%rbx),%r12w`。RBX 是非 canonical 位址 `0x80df000000000000`，RDI 對應 libc 的靜態字串 `LANGUAGE`。這確認失效的環境陣列項目讀取，而非資料庫／附件錯誤。
4. Chromium 該版本的字型初始化含執行期 `FC_FONTATIONS` 環境變數更動；上游後續明確記錄 getenv/setenv 競爭並將它提前到建立執行緒之前。這是吻合的來源路徑，尚未直接捕捉當次並行寫入者的堆疊。[145.0.7632.6 原始碼](https://chromium.googlesource.com/chromium/src/+/refs/tags/145.0.7632.6/ui/gfx/linux/fontconfig_util.cc)、[上游修正後說明](https://chromium.googlesource.com/chromium/src/+/main/ui/gfx/linux/fontconfig_util.cc)。
5. 自製無帳號資料的 C 重現程式，同時讀取環境變數與新增 20,000 個合成項目。舊 glibc 映像三次皆 exit 139；納入正式測試後亦於第一輪 exit 139，保留失敗即停止。glibc 2.41 已修復此類陣列生命週期問題。[glibc 修正紀錄](https://sourceware.org/pipermail/glibc-bugs/2025-July/059702.html)。

原本兩次歷史失敗沒有保存例外，不能逐筆證明同因。此修正針對現在可重現、已取得原生指令證據的故障。

## 實作

- Python 基底改為固定 digest 的 `3.12.12-slim-trixie`，實測 libc `2.41-12+deb13u1`；建置時檢查 glibc 至少 2.41。
- Python、Playwright 與 Chromium 版本不變；新舊 Chromium 執行檔 SHA-256 均為 `27e55cc30e487493b89b663085d6deeb0707be201a568657c922fac9076c317c`，Python 依賴版本也相同。
- 保持 headless-shell、資源限制、私有網路、唯讀 root 與驗證內容。不加入自動重試，不把先前失敗改成成功。
- `browser_failure.py` 驗證實際 Playwright 子程序 SIGSEGV／SIGABRT 的失敗判定、分類、stderr 遮蔽、無影片與清理；`libc_environment.py` 驗證真正的 libc 並行行為，已加入 acceptance 入口。
- 詳細取捨見 [ADR 0005](adr/0005-browser-libc-environment-race.md)。

## 初步修正驗收

- 新正式應用映像的 libc 競爭測試 20／20 通過，每次 20,000 次環境變數新增及多執行緒讀取。
- M6 真實容器矩陣：文件 13 個、庫存 13 個情境全部符合預期，包含完整還原、資料缺失／錯誤、權限、啟動失敗、必要檢查略過及建立資源與 journal 的時差回收。
- 新映像兩模板 SIGSEGV／SIGABRT 共四個情境全部通過。

較長重複驗證與六階段 crash/retry 另於完成後補記；本節不先行宣稱它們通過。

## 重跑方式

在 repo 根目錄的已授權 Linux／WSL 測試環境執行；輸出目錄必須是新的私有目錄。先執行 `python3 scripts/prepare-images.py`，再製作新 fixture，勿將舊 bundle 改用新映像鎖。

```sh
python3 tests/integration/libc_environment.py --runs 20 --output /tmp/crl-libc-new
python3 tests/integration/browser_failure.py --template document-app --output /tmp/crl-signals-new
python3 tests/integration/stability.py --template document-app --runs 20 --browser-repeats 20 --output /tmp/crl-repeat-new
```

庫存模板改用 `--template inventory-app` 及另一個輸出目錄。原生 libc 測試使用既有 GCC，編譯產物唯讀掛入無網路的專屬容器；不把 compiler 放進應用映像。

## 原始證據（WSL，未提交 Git）

| 位置 | 證據 |
|---|---|
| `/tmp/crl-flake-browser/` | 原設定的啟動 SIGSEGV 與當時資源觀測 |
| `/tmp/crl-browser-fix/stability-document/` | 被否決的 full Chromium 候選同樣失敗 |
| `/tmp/crl-rseq-disabled/` | 停用 glibc rseq 的候選仍失敗 |
| `/tmp/crl-kernel-baseline-2/`、`/tmp/crl-kernel-signal/signal.trace` | 核心 general-protection fault 路徑 |
| `/tmp/crl-native-registers/`、`/tmp/crl-native-analysis/` | 故障暫存器、固定映像二進位及 libc 對照 |
| `/tmp/crl-libc-regression-baseline/` | 正式 libc 測試在舊映像的首輪失敗 |
| `/tmp/crl-glibc-fix/` | 修正後版本、各套件結果、報告與影片 |
