import os
import sys
import random
from datetime import datetime, timedelta

import pytz
import requests


def calc_next_interval_seconds(start_minute: int, end_minute: int):
    """
    start_minute / end_minute: 从当天 0:00 开始算的分钟数，例如：
      0:10 => 10
      1:00 => 60
    """
    if end_minute <= start_minute:
        raise ValueError("TIME_RANGE_END must be greater than TIME_RANGE_START")

    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)

    # 明天 0 点
    tomorrow = (now + timedelta(days=1)).date()
    base = tz.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0))

    start = base + timedelta(minutes=start_minute)
    end = base + timedelta(minutes=end_minute)

    delta_seconds = int((end - start).total_seconds())
    offset = random.randint(0, delta_seconds)
    next_run = start + timedelta(seconds=offset)

    interval_seconds = int((next_run - now).total_seconds())
    if interval_seconds < 20:
        interval_seconds = 20  # Uptime Kuma 的最小间隔建议不低于 20 秒[web:53]

    return interval_seconds, next_run


def update_kuma_interval(start_minute: int, end_minute: int, monitor_id: int):
    kuma_url = os.environ["KUMA_URL"].rstrip("/")     # 例如 https://your-kuma-domain
    api_key = os.environ["KUMA_API_KEY"]              # Kuma API Key[web:70]

    interval_seconds, next_run = calc_next_interval_seconds(start_minute, end_minute)
    print(
        f"[schedule_next] Next run at (Asia/Shanghai): {next_run}, "
        f"interval = {interval_seconds} seconds, "
        f"range = {start_minute}-{end_minute} minutes, monitor_id = {monitor_id}"
    )

    url = f"{kuma_url}/api/monitor/edit"  # 内部编辑监控端点，字段以当前版本文档为准[web:57]

    headers = {
        "Authorization": f"Bearer {api_key}",  # 使用 API Key 认证[web:70]
        "Content-Type": "application/json",
    }

    payload = {
        "id": monitor_id,
        "interval": interval_seconds,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        print(f"[schedule_next] Failed to update monitor. Status: {resp.status_code}, Body: {resp.text}")
        resp.raise_for_status()
    else:
        print(f"[schedule_next] Monitor {monitor_id} interval updated to {interval_seconds} seconds")


def main():
    if len(sys.argv) != 4:
        print("Usage: python schedule_next.py <start_minute> <end_minute> <monitor_id>")
        print("Example: python schedule_next.py 10 60 150  # 0:10-1:00, monitor ID = 150")
        sys.exit(1)

    start_minute = int(sys.argv[1])
    end_minute = int(sys.argv[2])
    monitor_id = int(sys.argv[3])

    update_kuma_interval(start_minute, end_minute, monitor_id)


if __name__ == "__main__":
    main()
