"""Calculation defects reported in the v0.30.2 review, each reproduced and then pinned."""

from datetime import date, datetime, timedelta

from sidekick import progress, race, stats
from sidekick import reports as rp
from sidekick.analytics import insights as ins
from sidekick.analytics import running as rn
from sidekick.connectors.base import Samples
from sidekick.db import next_id

from test_race import ANCHOR, set_race, synced


def test_two_runs_on_one_day_both_count_in_the_race_week():
    conn = synced()
    set_race(conn, 60)
    a = next(x for x in rp.activities(conn, "fixture", "2026-09-28", ANCHOR.isoformat()))
    extra = {k: v for k, v in a.items() if k != "_id"}
    extra.update(id=next_id(conn, "activity"), source_id="second-run", moving_s=2400.0,
                 start_utc=(datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    conn.activity.insert_one(extra)
    w = race.week_plan(conn, "fixture", ANCHOR)
    day = next(s for s in w["sessions"] if s["date"] == a["local_date"])
    assert day["ran_minutes"] == round(((a["moving_s"] or 0) + 2400) / 60) and "second-run" in day["source_ids"]


def test_average_pace_uses_only_runs_with_both_distance_and_time(monkeypatch):
    acts = [{"distance_m": 1000.0, "moving_s": 600.0, "avg_hr": None, "elevation_gain_m": 0},
            {"distance_m": 1000.0, "moving_s": None, "avg_hr": None, "elevation_gain_m": 0}]
    monkeypatch.setattr(stats.rp, "activities", lambda conn, s, a, b: acts)
    b = stats.block(None, "x", date(2026, 9, 1), date(2026, 9, 28), None)
    assert b["pace_s_per_km"] == 600 and b["km_per_week"] == 0.5  # 10:00/km, not 5:00; distance still counts both


def run(day: str, hr_seconds: int, moving: float = 2700.0) -> ins.RunData:
    t = [float(i) for i in range(0, int(moving), 1)]
    hr = [175.0 if i < hr_seconds else None for i in range(len(t))]
    s = Samples(t, hr, [3.0] * len(t), [3.0 * x for x in t], [None] * len(t), [None] * len(t))
    return ins.RunData(day, day, datetime.fromisoformat(day + "T07:00"), "w", 3.0 * moving, moving, None, s, [], "steady")


def test_intensity_needs_heart_rate_over_most_of_each_run():
    zones = {"floors": [100, 120, 140, 155, 170], "method": "HR_MAX", "max_hr": 190}
    sparse = [run(f"2026-09-{d:02d}", 1) for d in range(1, 9)]
    assert ins.intensity_distribution(sparse, zones)["verdict"] == "not_enough_data"
    full = [run(f"2026-09-{d:02d}", 2700) for d in range(1, 9)]
    assert ins.intensity_distribution(full, zones)["verdict"] == "pattern"


def test_consistency_ignores_weeks_before_synced_history():
    today = date(2026, 10, 5)  # a Monday; the last 8 complete weeks start 10 Aug
    runs = [run((date(2026, 9, 7) + timedelta(weeks=w, days=d)).isoformat(), 0, 1800) for w in range(4) for d in (0, 2, 4)]
    i = ins.consistency(runs, today)
    assert i["verdict"] == "no_clear_pattern" and i["effect"]["cv"] == 0 and len(i["effect"]["weeks"]) == 4


def test_best_effort_finds_a_segment_that_starts_on_a_sample():
    # 10-second samples with a faster middle section: the best kilometre ends between two samples
    t, d, x = [], [], 0.0
    for k in range(60):
        t.append(10.0 * k)
        d.append(x)
        x += 40.0 if 10 <= k < 35 else 30.0
    s = Samples(t, [None] * 60, [None] * 60, d, [None] * 60, [None] * 60)

    def time_at(dist):  # when the track reaches `dist` metres
        k = next(k for k in range(59) if d[k] <= dist <= d[k + 1])
        return t[k] + (t[k + 1] - t[k]) * (dist - d[k]) / (d[k + 1] - d[k])
    exact = min(time_at(x0 + 1000) - time_at(x0) for x0 in [i / 10 for i in range(int((d[-1] - 1000) * 10))])
    assert abs(rn.best_efforts(s)["1k"]["elapsed_s"] - exact) < 0.15


def test_one_old_vo2_reading_is_not_evidence_of_stability(monkeypatch):
    today = date(2026, 10, 5)
    old = (46.0, today - timedelta(days=45))
    monkeypatch.setattr("sidekick.scores.vo2_on", lambda conn, s, d, t: old)
    assert progress.vo2_signal(None, "x", today)["direction"] is None
    monkeypatch.setattr("sidekick.scores.vo2_on", lambda conn, s, d, t: (46.2, today - timedelta(days=2)) if d == today else (47.0, today - timedelta(days=30)))
    assert progress.vo2_signal(None, "x", today)["direction"] == "declining"


def test_efficiency_needs_the_halves_to_agree(monkeypatch):
    today = date(2026, 10, 5)
    era = {"runs": 8, "end": "2026-10-01", "slope_s_per_km_per_30d": -6.0, "first_half_median_pace": 300, "second_half_median_pace": 310}
    monkeypatch.setattr(progress.rp, "latest_body", lambda conn, t: {"insights": [
        {"id": "efficiency", "effect": {"eras": [era], "band_bpm": [150, 159]}}]})
    assert progress.efficiency_signal(None, "x", today)["direction"] == "stable"  # 5:00 → 5:10 is not "improving"


class Reports:
    def __init__(self, rows):
        self.rows = rows

    def find(self, q, proj):
        return self

    def sort(self, k, d):
        return sorted(self.rows, key=lambda r: -r["revision"])


def test_durability_uses_only_each_runs_newest_revision():
    today = date(2026, 10, 5)
    rows = [{"subject_key": "a", "revision": 2, "body": {"local_date": "2026-10-01", "decoupling": {"eligible": False, "decoupling_pct": 9.0}}},
            {"subject_key": "a", "revision": 1, "body": {"local_date": "2026-10-01", "decoupling": {"eligible": True, "decoupling_pct": 2.0}}}]

    class Conn:
        report = Reports(rows)
    s = progress.drift_signal(Conn(), "x", today)
    assert "(0 so far)" in s["say"]  # the older eligible revision doesn't come back


def test_an_even_pace_over_noisy_elevation_is_steady():
    # 45 minutes at an even 3 m/s on flat ground, with recorded elevation drifting ±3 m every 30 s (barometer noise):
    # the hill-adjusted speed swings, the run doesn't
    import random
    rnd = random.Random(7)
    t = [float(i) for i in range(0, 2700, 2)]
    elev, e = [], 30.0
    for i in range(len(t)):
        if i % 15 == 0:
            e = 30.0 + rnd.choice((-3.0, 0.0, 3.0))
        elev.append(e)
    s = Samples(t, [150.0] * len(t), [3.0 + 0.05 * rnd.random() for _ in t], [3.0 * x for x in t], elev, [170.0] * len(t))
    graded = rn.with_gap(s)
    assert rn.speed_cv(graded) > rn.STEADY_MAX_CV  # what made runs "not steady" before
    assert rn.classify(graded, [], s)["kind"] == "steady"
    assert rn.decoupling(s, [], 8100.0, 20.0)["eligible"]
