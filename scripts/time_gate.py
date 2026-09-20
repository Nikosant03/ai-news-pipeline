"""Decide whether it's really 07:00 in Cyprus right now — GitHub Actions cron is
always UTC and has no DST awareness, so this runs on every trigger and skips the
wrong one. See design spec §7."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CYPRUS = ZoneInfo("Asia/Nicosia")


def is_seven_am_cyprus(now_utc: datetime) -> bool:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(CYPRUS).hour == 7


if __name__ == "__main__":
    import os

    result = is_seven_am_cyprus(datetime.now(timezone.utc))
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"should_run={'true' if result else 'false'}\n")
    print(f"should_run={result}")
