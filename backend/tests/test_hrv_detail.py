"""Garmin's 5-minute overnight HRV: the night's early/late/stage values, the night's shape against your usual, the
7-day stability (Plews), the day-before comparison and the Today/briefing hooks. Synthetic payloads in Garmin's shape."""
import math
from datetime import date, datetime, timedelta, timezone

from sidekick import health, hrv_detail as hd
from sidekick.connectors.base import DayBundle, Observation
from sidekick.db import connect, user_db_name
from sidekick.store import save_day

D = date(2026, 11, 3)
SRC = "garmin"


def gmt(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.0")


def payloads(day: date, early: float, late: float, hours: float = 7.0):
    """A night from 23:00 UTC: readings every 5 min, `early` for the first 3 h, `late` after; deep sleep the first hour."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) - timedelta(hours=1)
    n = int(hours * 12)
    rd = [{"hrvValue": early if k < 36 else late, "readingTimeGMT": gmt(start + timedelta(minutes=5 * k, seconds=30))} for k in range(n)]
    end = start + timedelta(minutes=5 * n)
    hrv = {"hrvSummary": {"lastNightAvg": round((early + late) / 2)}, "hrvReadings": rd,
           "sleepStartTimestampGMT": gmt(start), "sleepEndTimestampGMT": gmt(end), "sleepStartTimestampLocal": gmt(start + timedelta(hours=2))}
    sleep = {"sleepLevels": [{"startGMT": gmt(start), "endGMT": gmt(start + timedelta(hours=1)), "activityLevel": 0.0},
                             {"startGMT": gmt(start + timedelta(hours=1)), "endGMT": gmt(start + timedelta(hours=5)), "activityLevel": 1.0},
                             {"startGMT": gmt(start + timedelta(hours=5)), "endGMT": gmt(end), "activityLevel": 2.0}]}
    return hrv, sleep


def test_night_values_split_the_night_and_the_stages():
    hrv, sleep = payloads(D, 30.0, 42.0)
    v = hd.night_values(hrv, sleep)
    assert v["hrv_early_avg"] == 30.0 and v["hrv_late_avg"] == 42.0  # first 3 h and last 3 h (not overlapping)
    assert v["hrv_deep_avg"] == 30.0 and v["hrv_rem_avg"] == 42.0
    assert v["hrv_light_avg"] == round((24 * 30 + 24 * 42) / 48, 1)
    # Too short a night: nothing, never a guess
    assert all(x is None for x in hd.night_values(payloads(D, 30, 40, hours=1.5)[0], None).values())
    assert hd.night_values(None, None)["hrv_early_avg"] is None
    obs = hd.night_obs(D.isoformat(), hrv, sleep)
    assert {o.metric for o in obs} == {"hrv_early_avg", "hrv_late_avg", "hrv_deep_avg", "hrv_light_avg", "hrv_rem_avg"}


def store_nights(conn, nights: dict[date, tuple[float, float]], raw_last: bool = True):
    for d, (e, l) in nights.items():
        hrv, sleep = payloads(d, e, l)
        obs = hd.night_obs(d.isoformat(), hrv, sleep) + [Observation(d.isoformat(), "hrv_overnight_avg", (e + l) / 2, method="garmin_overnight_hrv")]
        save_day(conn, SRC, DayBundle(local_date=d.isoformat(), observations=obs))
        if raw_last and d == max(nights):
            conn.raw_payload.insert_one({"source": SRC, "kind": "hrv", "source_key": d.isoformat(), "payload": hrv})


def usual_nights(k_from: int = 28, k_to: int = 1):
    # A usual night: 36 early, 40 late, with a little night-to-night variation
    return {D - timedelta(days=k): (36.0 + (k % 3) - 1, 40.0 + (k % 2)) for k in range(k_from, k_to - 1, -1)}


def test_the_nights_shape_against_your_usual():
    conn = connect(user_db_name(1, "garmin"))
    store_nights(conn, {**usual_nights(), D: (28.0, 40.0)})
    n = hd.night(conn, SRC, D)
    assert n["status"] == "low_early" and "back to your usual by morning" in n["say"]
    assert len(n["curve"]) == 84 and n["curve"][0]["min"] == 0 and n["stages"]["deep"] == 28.0
    conn.daily_observation.update_one({"metric": "hrv_late_avg", "local_date": D.isoformat()}, {"$set": {"value": 33.0}})
    assert hd.night(conn, SRC, D)["status"] == "low_all_night"
    conn.daily_observation.update_many({"local_date": D.isoformat(), "metric": {"$in": ["hrv_early_avg", "hrv_late_avg"]}}, {"$set": {"value": 36.0}})
    assert hd.night(conn, SRC, D)["status"] == "usual"
    # Without a week of nights before, it is learning, never judged
    fresh = connect(user_db_name(2, "garmin"))
    store_nights(fresh, {D - timedelta(days=1): (36, 40), D: (28, 40)})
    assert hd.night(fresh, SRC, D)["status"] == "learning"


def test_seven_day_stability_follows_plews():
    conn = connect(user_db_name(1, "garmin"))
    # 8 weeks of baseline around 40 ms (a little swing), then a week around 32 ms swinging widely
    base = {D - timedelta(days=k): (40.0 + (2 if k % 2 else -2), 40.0 + (2 if k % 2 else -2)) for k in range(70, 6, -1)}
    week = {D - timedelta(days=k): (v, v) for k, v in zip(range(6, -1, -1), (26.0, 38.0, 25.0, 39.0, 27.0, 37.0, 30.0))}
    store_nights(conn, {**base, **week}, raw_last=False)
    s = hd.stability(conn, SRC, D)
    vals = [v for v, _ in week.values()]
    ln = [math.log(v) for v in vals]
    assert s["mean_ms"] == round(math.exp(sum(ln) / 7), 1)
    m = sum(ln) / 7
    assert s["cv_pct"] == round(100 * (sum((x - m) ** 2 for x in ln) / 7) ** 0.5 / m, 1)
    assert s["level"] == "below" and s["swing"] == "more" and s["status"] == "watch" and "isn't being absorbed" in s["say"]
    assert len(s["trend"]) == 42 and s["trend"][-1]["value"] == s["mean_ms"]
    # Too few nights this week: nothing
    conn.daily_observation.delete_many({"metric": "hrv_overnight_avg", "local_date": {"$gte": (D - timedelta(days=3)).isoformat()}})
    assert hd.stability(conn, SRC, D) is None


def add_run(conn, day: date, load: float):
    conn.report.insert_one({"id": f"r{day}", "type": "post_run", "subject_key": f"r{day}", "revision": 1, "local_date": day.isoformat(), "body": {"load": load}})


def test_day_before_stays_quiet_until_the_evidence_is_there():
    conn = connect(user_db_name(1, "garmin"))
    nights, k = {}, 0
    for i in range(80, 0, -1):
        d = D - timedelta(days=i)
        hard = i % 4 == 0          # a hard run every 4th day, an easier one the day after, rest otherwise
        if hard:
            add_run(conn, d, 150)
        elif i % 4 == 3:
            add_run(conn, d, 60)
        # the night after a hard run is 15% lower early on
        prev_hard = (i + 1) % 4 == 0
        nights[d] = (34.0 if prev_hard else 40.0 + (i % 3) - 1, 40.0)
    store_nights(conn, nights, raw_last=False)
    b = hd.day_before(conn, SRC, D)
    assert b["status"] == "shown" and b["hard_nights"] >= 10 and b["rest_nights"] >= 10 and "lower" in b["say"]
    # Only a few hard nights: it says what it still needs
    few = connect(user_db_name(2, "garmin"))
    for i in (10, 6):
        add_run(few, D - timedelta(days=i), 150)
    store_nights(few, {D - timedelta(days=i): (36, 40) for i in range(30, 0, -1)}, raw_last=False)
    q = hd.day_before(few, SRC, D)
    assert q["status"] == "learning" and "more nights after hard runs" in q["say"]


def test_today_row_and_briefing_carry_it_without_changing_the_advice():
    conn = connect(user_db_name(1, "garmin"))
    store_nights(conn, {**usual_nights(), D: (28.0, 40.0)})
    detail = hd.build(conn, SRC, D)
    body = {"findings": [{"metric": "hrv_overnight_avg", "observed": {"value": 34}, "status": "within", "delta": None, "sparkline": []}],
            "garmin_context": [], "hrv_detail": detail}
    row = next(r for r in health.build(body, conn, SRC, D)["rows"] if r["id"] == "hrv")
    assert row["has_detail"] is True and row["detail"].startswith("as usual · low early in the night")
    f = hd.findings(conn, SRC, D)
    assert [x["metric"] for x in f] == ["hrv_night_shape", "hrv_7d_stability"] and all(x["status"] == "info" for x in f)
    assert "First 3 hours of sleep 28 ms (usual 36)" in f[0]["statement"]
