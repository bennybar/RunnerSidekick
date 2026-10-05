from datetime import date, timedelta

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


def test_training_load_fades_and_counts_recent_effort():
    from datetime import datetime, timezone
    from sidekick.connectors.fixture import FixtureConnector
    from sidekick.db import connect, user_db_name
    from sidekick.sync import run_sync
    from sidekick import reports as rp
    anchor = date(2026, 9, 30)
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(anchor), anchor, 45, 3, max_backfill_days=60)
    zones = rp.hr_zones(conn)
    last = rp.activities(conn, "fixture", "2026-01-01", anchor.isoformat())[-1]
    end = datetime.fromisoformat(last["start_utc"].replace("Z", "+00:00"))
    soon = rd.training_load(conn, "fixture", end + timedelta(hours=14), zones)
    later = rd.training_load(conn, "fixture", end + timedelta(hours=62), zones)
    assert soon and later and soon["left_now"] > later["left_now"] > 0  # recent effort fades over days
    assert soon["fatigue"] >= later["fatigue"] == 0  # and two and a half days on, nothing is left above usual
    assert soon["ratio"] > later["ratio"] and soon["typical"] > 0


def test_short_history_is_not_read_as_a_load_spike(monkeypatch):
    from datetime import datetime, timezone
    at = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)

    def history(n):  # the same 30-minute run every day for n days
        return [{"id": k, "source_id": str(k), "moving_s": 1800, "start_utc": (at - timedelta(days=k, hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
                for k in range(n, 0, -1)]
    monkeypatch.setattr(rd, "run_load", lambda conn, a, floors: 60.0)
    monkeypatch.setattr(rd.rp, "get_setting", lambda conn, k, d: d)
    ratios = []
    for n in (22, 84):
        monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b, n=n: history(n))
        ratios.append(rd.training_load(None, "x", at, None)["ratio"])
    # Same training, different history length: the same reading (before the fix: 1.665 vs 0.997), and no "heavier"
    assert abs(ratios[0] - ratios[1]) < 0.05 and max(ratios) < rd.LOAD_OK


def morning(rule="R5", sleep_h=None):
    f = [{"metric": "sleep_duration", "observed": {"value": sleep_h * 3600}, "status": "learning"}] if sleep_h else []
    return {"findings": f, "recommendation": {"rule_id": rule, "state": "usual_plan", "suppress_intensity": False}}


def test_no_score_without_overnight_data_and_pain_overrides(monkeypatch):
    monkeypatch.setattr(rd.rp, "hr_zones", lambda conn: None)
    monkeypatch.setattr(rd, "moment", lambda conn, d: None)
    monkeypatch.setattr(rd, "training_load", lambda conn, s, at, z: {"ratio": 1.0, "fatigue": 0.0, "left_now": 0.5, "left_usual": 0.5, "last_when": None})
    monkeypatch.setattr(rd, "garmin_check", lambda conn, s, d, at: None)
    assert rd.build(None, "x", TODAY, morning())["status"] == "unavailable"  # load and recovery alone aren't enough
    ok = rd.build(None, "x", TODAY, morning(sleep_h=8))
    assert ok["status"] == "ok" and ok["score"] == 100
    pain = rd.build(None, "x", TODAY, morning("R0", sleep_h=8))
    assert pain["score"] <= rd.PAIN_CAP and pain["headline"] == "Take it easy or rest"


def daily(at, n=60, hours=1, extra=None):
    """The same 30-minute run every day including today, ending `hours` before `at`'s time of day; `extra`: {days ago: load}."""
    return [{"id": k, "source_id": str(k), "moving_s": 1800, "elapsed_s": 1800, "local_date": (at - timedelta(days=k)).date().isoformat(),
             "load": (extra or {}).get(k, 60.0),
             "start_utc": (at - timedelta(days=k, hours=hours, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")} for k in range(n, -1, -1)]


def test_a_steady_daily_routine_reads_as_recovered(monkeypatch):
    from datetime import datetime, timezone
    at = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(rd, "run_load", lambda conn, a, floors: a["load"])
    monkeypatch.setattr(rd.rp, "get_setting", lambda conn, k, d: d)
    monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b: daily(at))
    tl = rd.training_load(None, "x", at, None)
    assert tl["left_now"] > 0.4 and tl["fatigue"] < 0.05  # some effort always left, but that's normal for this routine
    # A much harder run yesterday on top of the routine still shows
    monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b: daily(at, extra={1: 180.0}))
    assert rd.training_load(None, "x", at, None)["fatigue"] > 0.8


def test_runs_are_found_by_local_date_and_end_on_elapsed_time(monkeypatch):
    from datetime import datetime, timezone
    at = datetime(2026, 10, 1, 21, 30, tzinfo=timezone.utc)  # 00:30 on 2 Oct in Israel, still 1 Oct in UTC
    asked = []
    monkeypatch.setattr(rd, "run_load", lambda conn, a, floors: a["load"])
    monkeypatch.setattr(rd.rp, "get_setting", lambda conn, k, d: "Asia/Jerusalem" if k == "timezone" else d)

    def acts(conn, s, a, b):
        asked.append(b)
        return daily(at, n=30)
    monkeypatch.setattr(rd.rp, "activities", acts)
    rd.training_load(None, "x", at, None)
    assert asked == ["2026-10-02"]  # the local day, not UTC's 1 Oct
    # A paused run: 30 min moving but 60 min elapsed hasn't finished 45 minutes after it started
    runs = daily(at, n=30)
    runs.append({"id": 99, "source_id": "99", "moving_s": 1800, "elapsed_s": 3600, "local_date": "2026-10-02", "load": 60.0,
                 "start_utc": (at - timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b: runs)
    assert rd.training_load(None, "x", at, None)["last_when"] != "today"


def test_the_weakest_part_caps_the_score_closer(monkeypatch):
    # The morning after a threshold run: HRV, resting HR and sleep normal, load 122% of usual, recovery 45 points
    monkeypatch.setattr(rd.rp, "hr_zones", lambda conn: None)
    monkeypatch.setattr(rd, "moment", lambda conn, d: None)
    monkeypatch.setattr(rd, "garmin_check", lambda conn, s, d, at: {"score": 1, "level": "poor", "recovery_hours": 52})
    monkeypatch.setattr(rd, "training_load", lambda conn, s, at, z: {"ratio": 1.22, "fatigue": 0.68, "left_now": 1.19, "left_usual": 0.5,
                                                                      "last_when": "yesterday"})
    r = rd.build(None, "x", TODAY, morning(sleep_h=7.1))
    rec = next(p for p in r["components"] if p["id"] == "recovery")["points"]
    assert r["score"] == rec + rd.CAP_ABOVE_LOWEST and r["label"] == "Moderate" and r["garmin"]["recovery_hours"] == 52


def test_garmin_recovery_timer_holds_intensity_back():
    from sidekick import decide
    rec = {"rule_id": "R5", "state": "usual_plan"}
    assert decide.hold_reason(rec, {"score": 80, "garmin": {"recovery_hours": 52}}).startswith("Garmin's recovery timer")
    assert decide.hold_reason(rec, {"score": 80, "garmin": {"recovery_hours": 10}}) is None
    assert decide.hold_reason(rec, {"score": 80, "garmin": None}) is None


def test_garmin_check_counts_down_the_recovery_timer():
    from datetime import datetime, timezone

    class Raw:
        def find_one(self, q, *a, **k):
            return {"payload": {"score": 1, "level": "POOR", "recoveryTime": 3142, "timestamp": "2026-10-02T03:45:33.0"}}

    class Conn:
        raw_payload = Raw()
    g = rd.garmin_check(Conn(), "garmin", TODAY, datetime(2026, 10, 2, 13, 45, 33, tzinfo=timezone.utc))
    assert g == {"score": 1, "level": "poor", "recovery_hours": 42}  # 52 h at 03:45 UTC, ten hours later
