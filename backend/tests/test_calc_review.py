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


def test_insight_confidence_needs_the_same_direction():
    up = {"verdict": "pattern", "headline": "Faster at the same heart rate: about 6 s/km per month"}
    up2 = {"verdict": "pattern", "headline": "Faster at the same heart rate: about 9 s/km per month"}
    down = {"verdict": "pattern", "headline": "Slower at the same heart rate recently"}
    assert rp.pattern_key(up) == rp.pattern_key(up2) and rp.pattern_key(up) != rp.pattern_key(down)


def test_compare_uses_the_same_dated_vo2_as_fitness(monkeypatch):
    from sidekick import compare
    from sidekick.db import set_setting
    conn = synced()
    set_setting(conn, "garmin_fitness", {"vo2max": {"value": 52.0, "date": "2026-05-01"}})  # an old snapshot
    monkeypatch.setattr("sidekick.scores.vo2_on", lambda c, s, d, t: None)
    item = next(i for i in compare.build(conn, "fixture", ANCHOR)["items"] if i["id"] == "vo2max")
    assert item["status"] == "unavailable"
    monkeypatch.setattr("sidekick.scores.vo2_on", lambda c, s, d, t: (47.0, ANCHOR))
    assert "47" in str(next(i for i in compare.build(conn, "fixture", ANCHOR)["items"] if i["id"] == "vo2max"))


def test_race_baseline_skips_unknown_weeks_but_counts_real_breaks(monkeypatch):
    conn = synced()
    set_race(conn, 60)
    full = race.week_plan(conn, "fixture", ANCHOR)["target_minutes"]
    # History starting last week: only that week is known, so it alone is the baseline
    monkeypatch.setattr("sidekick.scores.history_start", lambda c, s: date(2026, 9, 21))
    last_week = sum(a["moving_s"] or 0 for a in rp.activities(conn, "fixture", "2026-09-21", "2026-09-27"))
    w = race.week_plan(conn, "fixture", ANCHOR)
    assert abs(w["target_minutes"] * 60 - last_week * race.VOLUME_FACTOR["build"]) < 60 and full is not None
    # A week with no running inside known history is a real break and lowers the baseline
    monkeypatch.setattr("sidekick.scores.history_start", lambda c, s: date(2026, 1, 1))
    conn.activity.delete_many({"local_date": {"$gte": "2026-09-14", "$lte": "2026-09-20"}})
    conn.activity.delete_many({"local_date": {"$gte": "2026-09-07", "$lte": "2026-09-13"}})
    assert race.week_plan(conn, "fixture", ANCHOR)["target_minutes"] < full


def test_split_cadence_is_time_weighted():
    # 1 s samples at 160 spm for 3 minutes, then 10 s samples at 180 spm for a minute: 3/4 of the time at 160
    t = [float(i) for i in range(180)] + [180.0 + 10 * k for k in range(1, 7)]
    n = len(t)
    s = Samples(t, [150.0] * n, [3.0] * n, [3.0 * x for x in t], [10.0] * n, [160.0] * 180 + [180.0] * 6)
    d = rn.split_details(s, [{"idx": 0, "elapsed_s": 250.0}], None)
    assert 164 <= d[0]["cadence_spm"] <= 165  # an unweighted mean of the samples would say 161


def test_readiness_headline_and_next_run_follow_one_policy():
    from sidekick import decide
    rec = {"rule_id": "R5", "state": "usual_plan"}
    assert decide.allows(rec, {"score": 70}, None) == "steady"  # Moderate: steady at most, said as such
    assert decide.HEADLINES["steady"] == "Good for a steady run"
    assert decide.allows(rec, {"score": 70}, "Garmin's recovery timer still shows about 49 h") == "easy"
    assert decide.allows(rec, {"score": 80}, None) == "hard" and decide.allows(rec, {"score": 35}, None) == "rest"
    assert decide.allows({"rule_id": "R0", "state": "consider_easier"}, {"score": 90}, None) == "rest"


def test_moderate_readiness_turns_quality_into_steady_and_the_card_agrees(monkeypatch):
    from sidekick import decide, readiness as rd
    conn = synced()
    m = rp.build_morning(conn, "fixture", ANCHOR, False)
    monkeypatch.setattr(rd, "build", lambda c, s, d, mo: {"status": "ok", "score": 70, "label": "Moderate", "components": []})
    dec = decide.decide(conn, "fixture", ANCHOR, m)
    assert dec["readiness"]["headline"] == decide.HEADLINES[dec["allows"]]
    nr = dec["next_run"]
    if nr and nr["date"] == ANCHOR.isoformat():
        assert nr["kind"] not in ("tempo", "intervals", "race_pace")


def test_intensity_rejects_truncated_sample_files():
    zones = {"floors": [100, 120, 140, 155, 170], "method": "HR_MAX", "max_hr": 190}
    # 45-minute runs whose files hold only 60 s of (fully valid) heart rate
    cut = [run(f"2026-09-{d:02d}", 60, 60) for d in range(1, 9)]
    for r in cut:
        r.moving_s = 2700.0
    assert ins.intensity_distribution(cut, zones)["verdict"] == "not_enough_data"


def test_race_week_sessions_shrink_to_what_is_left(monkeypatch):
    conn = synced()
    set_race(conn, 60)
    w = race.week_plan(conn, "fixture", ANCHOR)
    left = w["target_minutes"] - w["done_minutes"]
    todo = [s for s in w["sessions"] if s["status"] in ("today", "planned") and s["kind"] not in ("race", "rest") and s["minutes"]]
    assert sum(s["minutes"] for s in todo if not s["optional"]) <= max(left, 0) + race.MIN_SESSION
    # Target already met: everything still to do is optional, short and easy
    monkeypatch.setattr(race, "VOLUME_FACTOR", {k: 0.1 for k in race.VOLUME_FACTOR})
    w = race.week_plan(conn, "fixture", ANCHOR)
    rest_of_week = [s for s in w["sessions"] if s["status"] in ("today", "planned") and s["kind"] not in ("race", "rest")]
    assert all(s["optional"] and s["kind"] == "easy" and s["minutes"] == race.MIN_SESSION for s in rest_of_week)


def test_one_improving_signal_is_an_early_sign(monkeypatch):
    from test_progress import fake
    p = fake(monkeypatch, "improving", "stable", "stable")
    assert p["summary"].startswith("Early signs of improvement") and p["agreement"] == "1 of 3 signals"
    p = fake(monkeypatch, "improving", "improving", "stable")
    assert p["summary"].startswith("You're getting fitter") and p["agreement"] == "2 of 3 signals"


def plan_week(sessions, done=0, target=60):
    return {"label": "City Half", "date": "2026-11-30", "phase": "build", "distance": "half",
            "week": {"week_start": "2026-09-28", "sessions": sessions, "done_minutes": done, "target_minutes": target}}


def next_run_with(monkeypatch, race_status, score=70, allowed="steady", hold=None):
    from sidekick import readiness as rd
    conn = synced()
    conn.activity.delete_many({"local_date": ANCHOR.isoformat()})  # today's session not run yet
    m = rp.build_morning(conn, "fixture", ANCHOR, False)
    ready = {"status": "ok", "score": score, "label": "Moderate", "components": []}
    return rd.next_run(conn, "fixture", ANCHOR, m, ready, race_status, hold=hold, allowed=allowed)


def test_a_tempo_turned_steady_keeps_the_plans_duration(monkeypatch):
    s = [{"date": ANCHOR.isoformat(), "kind": "tempo", "minutes": 10, "status": "today", "optional": False}]
    nr = next_run_with(monkeypatch, plan_week(s))
    assert nr["kind"] == "steady" and nr["minutes"] <= 10  # not the typical 60-minute run


def test_race_day_while_easy_only_says_so(monkeypatch):
    rs = plan_week([{"date": ANCHOR.isoformat(), "kind": "race", "minutes": None, "status": "today", "optional": False}])
    rs["date"] = ANCHOR.isoformat()
    nr = next_run_with(monkeypatch, rs, allowed="easy", hold="Garmin's recovery timer still shows about 49 h")
    assert nr["kind"] == "race" and "easy only" in nr["caution"] and "49 h" in nr["caution"]


def test_an_optional_session_stays_optional_in_the_next_run(monkeypatch):
    s = [{"date": ANCHOR.isoformat(), "kind": "easy", "minutes": 10, "status": "today", "optional": True}]
    nr = next_run_with(monkeypatch, plan_week(s, done=70, target=60), score=85, allowed="hard")
    assert nr["optional"] is True and any("target is already met" in w for w in nr["why"])


def test_a_held_back_session_without_an_easy_pace_keeps_the_plans_time(monkeypatch):
    s = [{"date": ANCHOR.isoformat(), "kind": "tempo", "minutes": 10, "status": "today", "optional": False}]
    real = rp.latest_body
    monkeypatch.setattr(rp, "latest_body", lambda conn, t, *a, **k: None if t == "insights" else real(conn, t, *a, **k))
    nr = next_run_with(monkeypatch, plan_week(s), allowed="easy", hold="Garmin's recovery timer still shows about 49 h")
    assert nr["kind"] == "easy" and nr["minutes"] == 10 and nr["distance_km"] is None  # a time, not a guessed 9 km


def test_race_caution_drops_the_target_pace(monkeypatch):
    rs = plan_week([{"date": ANCHOR.isoformat(), "kind": "race", "minutes": None, "status": "today", "optional": False}])
    rs.update(date=ANCHOR.isoformat(), target_pace_s_per_km=300)
    nr = next_run_with(monkeypatch, rs, allowed="easy", hold="Garmin's recovery timer still shows about 49 h")
    assert nr["caution"] and nr["pace"] is None and nr["pace_s_per_km"] is None
    calm = next_run_with(monkeypatch, rs, score=85, allowed="hard")
    assert calm["caution"] is None and calm["pace"] == "around 5:00 /km"
