# 2026 旅行工具

Bill 2026 年旅行用嘅小工具。

## 嵯峨野小火車有位通知（`sagano/`）

每 1 分鐘查一次11/29、11/30、12/1 嵯峨野小火車嘅剩餘位數。任何一日、任何一個方向有 **2 個位或以上**，就用 ntfy 推送通知去手機。

- 去程：嵯峨 → 龜岡（要揀 3 點後嘅班次）
- 回程：龜岡 → 嵯峨／嵐山（要揀 2 點前嘅班次）
- 訂票網：https://ars-saganokanko.triplabo.jp/activity/zt/LINKTIVITY-YRBTL

**限制：** 個訂票網只顯示「成日、每個方向」剩幾多位。收到通知之後，要自己入去揀班次時間，同埋揀並排嘅位（例如 1A 同 1B）。個工具唔會自動訂票。

### 設定步驟

1. 手機裝 **ntfy** App，撳「+」，訂閱一個人哋估唔到嘅主題名（例如 `bill-sagano-8f3k2q`）。
2. 去 GitHub：Settings → Secrets and variables → Actions → New repository secret。Name 填 `NTFY_TOPIC`，Value 填你嘅主題名。
3. 去 Actions → 小火車有位通知 → Run workflow，剔「推一個測試通知」，再撳 Run。手機收到通知就代表設定成功。

### 改設定

喺 `.github/workflows/sagano-watch.yml` 改：
- `DATES`：要查嘅日子
- `MIN_SEATS`：最少幾多個位先通知

### 點樣一直跑

每次執行連續查大約 25 分鐘，完咗自己觸發下一次。GitHub 排程只係後備。想停就去 Actions 頁撳「Disable workflow」。過咗 12/1 會自動停。
