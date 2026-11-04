# ADR 0001：以唯讀文件 API 建立第一個恢復 fixture

- 日期：2026-11-04
- 狀態：接受；容器整合驗證待完成

協調器依專案計畫採 Go。被還原的示範應用使用 Python 標準庫 HTTP server 與 psycopg，降低 fixture 的程式量，讓資料庫與附件故障容易重現。第一部分不建立產品 CLI。

PostgreSQL 暫定 major 17，映像 tag 17.6-bookworm；Python 映像 3.12.12-slim-bookworm；psycopg 3.3.7。這些是明確的實作候選版本，不代表已完成映像取得或相容性驗收，後續需記錄 Linux/Docker/Compose 實測版本及 digest。

資料只由顯式 seed 寫入；serve 不執行遷移、不補資料、不修改附件。API 提供登入、搜尋、下載，下載核對 DB 保存的 SHA-256。這讓有效 DB dump 搭配缺件或錯件備份的故障可以被觀察。新增寫入 API 前必須先完成維護模式與寫入排空協定。

目前單元測試使用 fake storage，驗證 HTTP 行為及檔案檢查；真正 PostgreSQL 行為需另跑 compose 與 smoke.py，不把 mock 當整合證據。

參考：[psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)、[Compose internal networks](https://docs.docker.com/reference/compose-file/networks/)。internal 設定不替代待實作的對外連線阻擋測試。
