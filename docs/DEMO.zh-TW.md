# 展示錄影

`scripts/record-demo.py` 使用實際報告製作約 185 秒的瀏覽器證據導覽。它不是即時執行的錄影，也不以影片長度代表還原耗時。

準備一份 JSON，四個值分別指向已產生的完整文件還原、缺附件、崩潰回收與完整庫存還原 report.json：

```json
{
  "complete": "/private/evidence/complete/report.json",
  "missing": "/private/evidence/missing/report.json",
  "crash": "/private/evidence/interrupted/report.json",
  "inventory": "/private/evidence/inventory/report.json"
}
```

```sh
python3 scripts/record-demo.py --evidence /private/demo-input.json \
  --images examples/document-app/images.lock.json \
  --output reports/recovery-walkthrough.webm
```

腳本先核對四份報告為 passed、failed、inconclusive、passed，再使用無網路、唯讀 rootfs 的容器錄製。文字與檢查表來自報告，沒有捏造執行結果。應用本身的真實登入／搜尋／下載錄影則在個別 attempt 的 browser.webm。

分享前只選擇合成資料的報告；錄影與執行產物不提交 Git。
