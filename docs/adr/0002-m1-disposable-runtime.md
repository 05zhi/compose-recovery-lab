# ADR 0002：M1 使用固定模板與可核對所有權的 disposable Compose runtime

- 日期：2026-11-04
- 狀態：接受

M1 先驗證從備份包恢復整個合成文件應用的垂直切片。Go 控制程式使用標準庫與結構化 Docker CLI 參數，產生固定 Compose JSON；不載入任意 Compose，避免尚未有明確允許清單時默默接受 host mounts、外部資源或公開 ports。

DB、應用、network、volumes 由隨機 run ID 隔離，資源建立前寫入 JSON intent。清理用 Docker discovery 補回中斷時尚未寫入的 ID，檢查 run label、Compose project label 和完整 ID 後逐項刪除。容器優先，其後 network 與 volumes；禁止全域 prune。已知的 cleanup failure 必須使 CLI 非零，即使驗證通過。

來源也是本工具建立的合成 fixture，備份時停止應用，並以獨立 context 在失敗時嘗試重新啟動。應用目前沒有寫入 API；外部 writer 不在支援範圍。備份以 `.partial` 寫入並原子發布；還原使用私有複本及受限制 tar。

演練 DB 先以 bootstrap 角色建立非 superuser 的 demo owner，dump/restore/app 使用 demo。還原不重建來源 owner/ACL，登入密碼以演練隨機值替換。這些取捨明列報告；不能推論原有帳號管理／正式 ACL 已驗證。

映像在準備階段取得，runtime 僅允許本機 image ID/digest。Compose 內網與外部 TCP endpoint 測試一起驗證有限隔離；不將其描述為 hostile-code sandbox。

M1 暫用 private JSON journal 和 HTML/JSON 報告。SIGTERM 可清理；SIGKILL 後需要明確 `cleanup --run-dir`。不從中斷 DB 續跑。SQLite 歷史、完整階段 journal、自動對帳／新 attempt retry 保留給 M3，避免把 M1 的單點中斷測試視為 M3 全部完成。
