from sidekick import readings


def f(metric, value, status, delta=None):
    return {"metric": metric, "observed": {"value": value}, "status": status, "delta": {"abs": delta} if delta is not None else None}


def test_verdicts_compare_with_your_range_and_your_age_group():
    cmp = {"items": [{"id": "resting_hr", "status": "ok", "lower_than_pct": 96, "group": "men aged 40–59", "value": 50},
                     {"id": "vo2max", "status": "ok", "value": 46.2, "rating": "Good", "group": "men aged 40–49", "percentile": 79}]}
    n = readings.notes([f("resting_hr", 49, "within"), f("sleep_duration", 6 * 3600, "outside", -3600),
                        f("hrv_overnight_avg", 39, "learning"), {"metric": "running_moving_time_7d", "observed": None, "status": "missing",
                                                                  "last": {"date": "2026-10-01", "value": 1}}], cmp)
    assert n["resting_hr"]["verdict"] == ("49 bpm today, within your usual range. Very good: your typical 50 bpm is lower than about "
                                          "96% of men aged 40–59.")
    assert "short of the 7 hours" in n["sleep_duration"]["verdict"] and "below your usual range" in n["sleep_duration"]["verdict"]
    assert n["hrv_overnight_avg"]["verdict"] == "39 ms. Your own usual range is still being learned."
    assert n["running_moving_time_7d"]["verdict"].startswith("Not in yet today")
    assert "higher than about 79%" in n["vo2max"]["verdict"] and all(x["meaning"] for x in n.values())
