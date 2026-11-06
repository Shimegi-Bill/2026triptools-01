#!/usr/bin/env python3
"""嵯峨野小火車 有位通知（GitHub Actions 用）

做咩：讀 Triplabo（LINKTIVITY）嘅公開日曆 API，睇指定日子、指定方向仲有幾多位。
      位數 >= MIN_SEATS 就用 ntfy 推送最高優先級（urgent）通知，有位期間一直重複，冇咗位再通知一次。
限制：API 只係出「成日、每個方向」嘅剩餘位數，冇班次時間同座位號；
      時間（去程 3 點後、回程 2 點前）同係咪連位，要收到通知之後自己入網站揀。
只用 Python 標準庫，唔使 pip install。

環境變數：
  NTFY_TOPIC   ntfy 主題名（必須，放 GitHub Secret）
  DATES        要睇嘅日子，逗號分隔，例如 2026-11-29,2026-11-30,2026-12-01
  MIN_SEATS    最少幾多個位先通知（預設 2）
  STATE_FILE   記住上次結果嘅檔案（預設 sagano_state.json）
  LOOP_SECONDS 一次執行入面連續查幾多秒（預設 0 = 查一次）
  INTERVAL_SECONDS 每次查相隔幾多秒（預設 60）
  FORCE_TEST   設做 1 就無論有冇位都推一個測試通知
"""
import base64
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

ACTIVITY = "LINKTIVITY-YRBTL"
API = f"https://ars-backend.triplabo.jp/v2/activity/calendar/zt/{ACTIVITY}"
BOOK_URL = f"https://ars-saganokanko.triplabo.jp/activity/zt/{ACTIVITY}"
PLANS = {
    "SAGANO-YRBTL-1": "去程 嵯峨→龜岡（揀3點後）",
    "SAGANO-YRBTL-2": "回程 龜岡→嵯峨/嵐山（揀2點前）",
}
# 冇呢個 header，API 會答「missing supplier metadata」
HEADERS = {
    "grpc-metadata-supplier": "saganokanko",
    "x-origin": "https://ars-saganokanko.triplabo.jp",
    "referer": "https://ars-saganokanko.triplabo.jp/",
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (personal seat-availability watcher)",
}
JST = timezone(timedelta(hours=9))


def fetch_calendar():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    cal = data.get("availabilityCalendar")
    if not cal:
        raise RuntimeError(f"API 冇日曆資料：{json.dumps(data, ensure_ascii=False)[:300]}")
    return cal.get("dailyAvailabilities", [])


def seats_by_date_plan(days, dates):
    """回傳 {"2026-11-29|SAGANO-YRBTL-1": 位數}，冇資料當 0。"""
    out = {f"{d}|{p}": 0 for d in dates for p in PLANS}
    for day in days:
        if day.get("date") not in dates:
            continue
        for t in day.get("timeAvailabilities", []):
            for pa in t.get("planAvailabilities", []):
                key = f"{day['date']}|{pa.get('planId')}"
                if key in out and pa.get("status") == "OK":
                    out[key] += int(pa.get("allotmentQuantity") or 0)
    return out


def notify(topic, title, body, priority="high"):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode("utf-8"),
        headers={
            # HTTP header 唔收得中文，用 RFC 2047 包住標題
            "Title": "=?UTF-8?B?" + base64.b64encode(title.encode()).decode() + "?=",
            "Priority": priority,
            "Tags": "train,rotating_light" if priority == "urgent" else "train",
            "Click": BOOK_URL,
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=30).read()


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        sys.exit("未設 NTFY_TOPIC（GitHub → Settings → Secrets → Actions）")
    dates = [d.strip() for d in os.environ.get("DATES", "2026-11-29,2026-11-30,2026-12-01").split(",") if d.strip()]
    min_seats = int(os.environ.get("MIN_SEATS", "2"))
    state_file = os.environ.get("STATE_FILE", "sagano_state.json")

    today = datetime.now(JST).strftime("%Y-%m-%d")
    dates = [d for d in dates if d >= today]
    if not dates:
        print("所有日子已經過咗，唔再查。可以刪走 .github/workflows/sagano-watch.yml")
        return

    try:
        prev = json.load(open(state_file, encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}

    # 一次 GitHub 執行入面重複查幾次（GitHub 排程最密每 5 分鐘）
    loop_seconds = int(os.environ.get("LOOP_SECONDS", "0"))
    interval = int(os.environ.get("INTERVAL_SECONDS", "60"))
    end_at = time.monotonic() + loop_seconds
    force_test = os.environ.get("FORCE_TEST") == "1"
    while True:
        try:
            prev = check_once(topic, dates, min_seats, prev, force_test)
            force_test = False
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(prev, f, ensure_ascii=False)
        except Exception as e:  # 網站一次答唔到就下次再試，唔好成個停
            print("今次查唔到：", e)
        if time.monotonic() + interval > end_at:
            break
        time.sleep(interval)


REPEAT_FAST = 10   # 有位嘅頭 10 次：每次查都響（大約每 1 分鐘）
REPEAT_SLOW = 10   # 之後：每 10 次先響一次（大約每 10 分鐘），唔好成晚嘈


def check_once(topic, dates, min_seats, state, force_test):
    """state = {"seats": {key: 位數}, "alerts": {key: 有位之後響咗幾次}}"""
    if "seats" not in state:  # 舊格式（直接係位數）
        state = {"seats": state, "alerts": {}}
    alerts = dict(state.get("alerts", {}))
    now = seats_by_date_plan(fetch_calendar(), dates)
    stamp = datetime.now(JST).strftime("%m/%d %H:%M:%S")
    print(f"{stamp} JST  " + "  ".join(f"{k[5:10]}{'去' if k.endswith('1') else '回'}:{now[k]}" for k in sorted(now)))

    # 有位就一直響，直到冇位為止：頭 10 次每分鐘響，之後每 10 分鐘響
    ring = []
    for k in sorted(now):
        if now[k] >= min_seats:
            n = alerts.get(k, 0)
            if n < REPEAT_FAST or (n - REPEAT_FAST) % REPEAT_SLOW == REPEAT_SLOW - 1:
                ring.append(k)
            alerts[k] = n + 1
        elif alerts.pop(k, 0):
            notify(topic, "小火車：啱啱個位冇咗",
                   f"{k[5:10].replace('-', '/')} {PLANS[k.split('|')[1]]}：而家剩 {now[k]} 位，繼續幫你睇住", "default")
            print("已通知冇位：", k)

    if ring:
        lines = [f"{k.split('|')[0][5:].replace('-', '/')} {PLANS[k.split('|')[1]]}：剩 {now[k]} 位" for k in ring]
        lines.append("⚠️ 時間啱就即刻訂住先（之後可以改座位換連位），乘車前一日取消免費")
        notify(topic, "🚨 小火車有位！快啲訂", "\n".join(lines), "urgent")
        print("已通知（urgent）：", ring)
    elif force_test:
        notify(topic, "小火車監察測試", f"{stamp} 測試正常。而家：" + "，".join(f"{k[5:10]} {k[-1]}號方案 {v}位" for k, v in sorted(now.items())), "urgent")
        print("已推測試通知")
    return {"seats": now, "alerts": alerts}


if __name__ == "__main__":
    main()
