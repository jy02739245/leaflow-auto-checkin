import sys
import random
from datetime import datetime, timedelta

import pytz
from uptime_kuma_api import UptimeKumaApi  # pip install uptime-kuma-api


def calc_next_interval_seconds(start_minute: int, end_minute: int):
    if end_minute <= start_minute:
        raise ValueError("TIME_RANGE_END must be greater than TIME_RANGE_START")

    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)

    tomorrow = (now + timedelta(days=1)).date()
    base = tz.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0))

    start = base + timedelta(minutes=start_minute)
    end = base + timedelta(minutes=end_minute)

    delta_seconds = int((end - start).total_seconds())
    offset = random.randint(0, delta_seconds)
    next_run = start + timedelta(seconds=offset)

    interval_seconds = int((next_run - now).total_seconds())
    if interval_seconds < 20:
        interval_seconds = 20
    return interval_seconds, next_run


def main():
    if len(sys.argv) != 4:
        print("Usage: python schedule_next.py <start_minute> <end_minute> <monitor_id>")
        sys.exit(1)

    start_minute = int(sys.argv[1])
    end_minute = int(sys.argv[2])
    monitor_id = int(sys.argv[3])

    kuma_url = os.environ["KUMA_URL"].rstrip("/")
    kuma_user = os.environ["KUMA_USER"]
    kuma_pass = os.environ["KUMA_PASS"]

    interval_seconds, next_run = calc_next_interval_seconds(start_minute, end_minute)
    print(
        f"[schedule_next] Next run at (Asia/Shanghai): {next_run}, "
        f"interval = {interval_seconds} seconds, "
        f"range = {start_minute}-{end_minute} minutes, monitor_id = {monitor_id}"
    )

    api = UptimeKumaApi(kuma_url)
    api.login(kuma_user, kuma_pass)

    # 这里直接调用官方封装的 edit_monitor，内部会通过 Socket.IO 调用 editMonitor 事件。[web:11][web:91]
    api.edit_monitor(monitor_id, interval=interval_seconds)

    api.disconnect()


if __name__ == "__main__":
    main()
