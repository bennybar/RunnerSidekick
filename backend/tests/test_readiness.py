from datetime import date

from sidekick import readiness as rd

TODAY = date(2026, 10, 2)


def f(metric, value, median=None, spark=None):
    return {"metric": metric, "observed": {"value": value}, "comparison": {"median": median} if median else None,
            "sparkline": spark or [], "status": "within" if median else "learning"}


def test_usual_falls_back_to_recent_days_while_range_is_learned():
    spark = [{"date": f"2026-09-{d}", "value": v} for d, v in (("27", 40), ("28", 44), ("29", 42), ("30", 46))]
    assert rd.usual(f("hrv_overnight_avg", 30, spark=spark), TODAY) == (43.0, "your last 4 days (provisional)")
    assert rd.usual(f("hrv_overnight_avg", 30, spark=spark[:3]), TODAY)[0] is None
    assert rd.usual(f("resting_hr", 50, median=48), TODAY) == (48, "your usual")


def test_missing_today_uses_yesterday_only():
    m = {"observed": None, "last": {"date": "2026-10-01", "value": 7}}
    assert rd.current(m, TODAY) == (7, "yesterday's value")
    assert rd.current({"observed": None, "last": {"date": "2026-09-29", "value": 7}}, TODAY) == (None, None)


def test_labels():
    assert [rd.label(x) for x in (90, 75, 60, 49)] == ["High", "High", "Moderate", "Low"]
