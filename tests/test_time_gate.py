from datetime import datetime, timezone
from scripts.time_gate import is_seven_am_cyprus


def test_summer_0400_utc_is_seven_am_cyprus():
    # EEST (UTC+3) — last Sunday of March through last Sunday of October
    dt = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    assert is_seven_am_cyprus(dt) is True


def test_winter_0500_utc_is_seven_am_cyprus():
    # EET (UTC+2)
    dt = datetime(2026, 1, 15, 5, 0, tzinfo=timezone.utc)
    assert is_seven_am_cyprus(dt) is True


def test_winter_0400_utc_is_not_seven_am_cyprus():
    dt = datetime(2026, 1, 15, 4, 0, tzinfo=timezone.utc)
    assert is_seven_am_cyprus(dt) is False


def test_summer_0500_utc_is_not_seven_am_cyprus():
    dt = datetime(2026, 7, 15, 5, 0, tzinfo=timezone.utc)
    assert is_seven_am_cyprus(dt) is False
