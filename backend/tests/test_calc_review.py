"""Calculation defects reported in the v0.30.2 review, each reproduced and then pinned."""

from datetime import date, datetime, timedelta, timezone

from sidekick import progress, race, stats
from sidekick import reports as rp
from sidekick.analytics import insights as ins
from sidekick.analytics import running as rn
from sidekick.connectors.base import Samples
from sidekick.db import next_id, utc_now

from test_race import ANCHOR, set_race, synced
from test_readiness import daily


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

    class NoWeather:
        def find(self, *a, **k):
            return []

    class Conn:
        report = Reports(rows)
        run_weather = NoWeather()
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
    assert rn.speed_cv(graded) > rn.speed_cv(s)  # elevation noise makes the hill-adjusted speed look less even
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


def test_manual_sync_waits_only_for_garmin():
    from datetime import timezone
    from sidekick.sync import next_manual_sync, set_connection
    conn = synced()
    now = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    conn.sync_job.insert_one({"id": next_id(conn, "sync_job"), "source": "fixture", "outcome": "ok",
                              "finished_at": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
    assert next_manual_sync(conn, "fixture", now) is None  # a sync a minute ago doesn't hold the next one back
    set_connection(conn, "fixture", retry_not_before=(now + timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert next_manual_sync(conn, "fixture", now) == now + timedelta(minutes=40)  # Garmin asked us to wait: we do


def test_ai_calls_on_the_server_key_share_one_daily_cap(monkeypatch):
    from sidekick import narrative as nv
    from sidekick.accounts import app_db
    from sidekick.db import connect, user_db_name
    monkeypatch.setenv("RSK_AI_MAX_CALLS_ALL", "3")
    app_db().counters.delete_many({})
    users = [connect(user_db_name(u, "fixture")) for u in (11, 12)]
    for c in users:
        c.counters.delete_many({}); c.ai_call.delete_many({})
    got = [nv.reserve_call(users[k % 2], "coach", 25) for k in range(5)]
    assert sum(g is not None for g in got) == 3  # three for both users together, each well under their own 25
    assert nv.reserve_call(users[0], "coach", 25, server_key=False) is not None  # the runner's own key isn't capped by it


def test_only_allowed_models_run_on_the_server_key(monkeypatch):
    from sidekick import narrative as nv
    monkeypatch.setenv("RSK_AI_MODELS", "gpt-6.1-sol-mini")
    assert nv.server_models() == {nv.DEFAULT_MODEL, "gpt-6.1-sol-mini"}


def test_one_bad_record_doesnt_stop_the_sync_and_syncs_dont_overlap():
    from sidekick.connectors.fixture import FixtureConnector
    from sidekick.db import connect, user_db_name
    from sidekick.sync import release_lease, run_sync, take_lease

    class Odd(FixtureConnector):
        def read_activity(self, s):
            if s["source_id"].endswith("3"):
                raise ValueError("activity has no startTimeGMT")
            return super().read_activity(s)
    conn = connect(user_db_name(31, "fixture"))
    for c in conn.list_collection_names():
        conn[c].drop()
    res = run_sync(conn, Odd(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    assert res.outcome == "ok" and res.skipped and "couldn't be read" in res.detail and conn.activity.count_documents({}) > 0
    # Another sync for the same user while one holds the lease is deferred, not run twice
    now = datetime.now(timezone.utc)
    assert take_lease(conn, now)
    assert run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3).outcome == "deferred"
    release_lease(conn)
    assert run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3).outcome == "ok"


def weekly_runs(at, hard_weekday, hard_load):
    """12 weeks of three 45-minute runs plus one bigger session on hard_weekday, each at 06:00."""
    runs = []
    for k, day in enumerate(range(84, 0, -1)):
        d = at - timedelta(days=day)
        if d.weekday() in (0, 3, hard_weekday) or d.weekday() == hard_weekday:
            load = hard_load if d.weekday() == hard_weekday else 90.0
            runs.append({"id": k, "source_id": str(k), "moving_s": 2700, "elapsed_s": 2700, "load": load,
                         "local_date": d.date().isoformat(), "start_utc": d.replace(hour=6).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return runs


def readiness_with(monkeypatch, at, runs):
    from sidekick import readiness as rd
    from test_readiness import morning
    monkeypatch.setattr(rd, "run_load", lambda conn, a, floors: a["load"])
    monkeypatch.setattr(rd.rp, "get_setting", lambda conn, kk, d: d)
    monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b: runs)
    monkeypatch.setattr(rd.rp, "hr_zones", lambda conn: None)
    monkeypatch.setattr(rd, "moment", lambda conn, d: at)
    monkeypatch.setattr(rd, "garmin_check", lambda conn, s, d, a: None)
    return rd.build(None, "x", at.date(), morning(sleep_h=8))


def test_the_day_after_a_weekly_long_run_or_hard_session_is_easy_not_rest(monkeypatch):
    # Sunday after the usual 90-minute Saturday, and Wednesday after the usual Tuesday intervals: everything else fine
    for at, wd, load in ((datetime(2026, 10, 4, 7, tzinfo=timezone.utc), 5, 220.0), (datetime(2026, 10, 7, 7, tzinfo=timezone.utc), 1, 260.0)):
        r = readiness_with(monkeypatch, at, weekly_runs(at, wd, load))
        rec = next(p for p in r["components"] if p["id"] == "recovery")
        assert rec["points"] < 85  # still recovering from it: shown, not hidden by "it's always like this"
        assert r["score"] >= 50  # but alone it holds the day to easy, never to rest


def test_one_short_night_holds_to_easy_not_rest(monkeypatch):
    from sidekick import readiness as rd
    from test_readiness import morning, TODAY
    monkeypatch.setattr(rd.rp, "hr_zones", lambda conn: None)
    monkeypatch.setattr(rd, "moment", lambda conn, d: None)
    monkeypatch.setattr(rd, "garmin_check", lambda conn, s, d, at: None)
    monkeypatch.setattr(rd, "training_load", lambda conn, s, at, z: {"ratio": 1.0, "fatigue": 0.0, "left_now": 0.5, "left_usual": 0.5,
                                                                      "last_when": None})
    r = rd.build(None, "x", TODAY, morning(sleep_h=4.5))
    assert r["score"] == rd.SINGLE_SIGNAL_FLOOR and r["label"] == "Moderate"  # easy (held below 60), not rest (under 40)


def test_downhill_credit_is_limited_and_an_out_and_back_hill_isnt_drift():
    # 4:00/km at −10%: Minetti alone would call it 6:41 on the flat; floored, at most 15% easier
    assert rn.DOWNHILL_FLOOR == 0.85 and rn.minetti_cost(-0.10) / rn.minetti_cost(0.0) < 0.6
    t = [float(x) for x in range(0, 4201, 5)]
    half = t[len(t) // 2]
    grade = [0.04 if x < half else -0.04 for x in t]  # up the hill, then back down
    dist, elev = [0.0], [0.0]
    for k in range(1, len(t)):
        dist.append(dist[-1] + 3.0 * 5)
        elev.append(elev[-1] + 3.0 * 5 * grade[k - 1])
    s = Samples(t, [150.0] * len(t), [3.0] * len(t), dist, elev, [170.0] * len(t))
    r = rn.decoupling(s, [], dist[-1], 84.0)
    assert not r["eligible"] and any("climb differently" in x for x in r["reasons"])


def test_the_week_after_a_race_keeps_easy_running_days():
    conn = synced()
    set_race(conn, -3, dist="half")  # raced three days ago: recovery phase
    w = race.week_plan(conn, "fixture", ANCHOR)
    assert w["phase"] == "recovery"
    kinds = [s["kind"] for s in w["sessions"]]
    assert "easy" in kinds and "long" not in kinds  # not seven rest days, and nothing long or hard
    assert not any(s["status"] == "extra" for s in w["sessions"] if s["kind"] != "rest")


def test_shallow_hills_get_modest_adjustment():
    # 3% up counts ~10% harder and 3% down ~6% easier (heart-rate-based models), not Minetti's +17% / −15%
    t = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    for grade, expect in ((0.03, 1.105), (-0.03, 0.94), (-0.20, rn.DOWNHILL_FLOOR)):
        dist = [30.0 * k for k in range(len(t))]
        elev = [d * grade for d in dist]
        s = Samples(t, [150.0] * len(t), [3.0] * len(t), dist, elev, [170.0] * len(t))
        g = [x for x in rn.gap_speeds(s) if x]
        assert abs(g[-1] / 3.0 - expect) < 0.01, (grade, g[-1] / 3.0)


def test_a_day_garmin_cant_read_is_skipped_not_fatal():
    from sidekick.connectors.fixture import FixtureConnector
    from sidekick.db import connect, user_db_name
    from sidekick.sync import run_sync

    class BadDay(FixtureConnector):
        def read_days(self, start, end):  # lazy, like Garmin's: the error comes while iterating
            for b in super().read_days(start, end):
                if b.local_date == "2026-09-20":
                    raise ValueError("odd sleep payload")
                yield b
    conn = connect(user_db_name(32, "fixture"))
    for c in conn.list_collection_names():
        conn[c].drop()
    res = run_sync(conn, BadDay(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    assert res.outcome == "ok" and "day:2026-09-20" in res.skipped and conn.activity.count_documents({}) > 0
    assert run_sync(conn, BadDay(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60).outcome == "ok"  # and the next sync isn't stuck


def test_every_fade_uses_the_same_threshold():
    from sidekick import focus
    from sidekick.analytics import insights as ins_mod
    assert focus.FADE_TARGET_S == rn.FADE_S_PER_KM
    import inspect
    src = inspect.getsource(ins_mod.pacing_pattern)
    assert "rn.FADE_S_PER_KM" in src and "+ 5" not in src and "- 5" not in src  # the insight reads the one threshold, no copy


def test_absurd_dates_are_refused_before_anything_changes(tmp_path):
    from sidekick.auth import create_token
    from test_multiuser import client
    c = client(tmp_path)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    assert c.get("/v1/today", params={"date": "0001-01-01"}, headers=h).status_code == 422
    assert c.delete("/v1/plan/junk", headers=h).status_code == 422


def test_a_hot_humid_run_is_said_to_be_hot_and_its_drift_isnt_poor_durability():
    from sidekick import run_checks, weather
    conn, sid = None, None
    conn = synced()
    a = rp.activities(conn, "fixture", "2026-09-01", ANCHOR.isoformat())[-1]
    sid = a["source_id"]
    conn.run_weather.update_one({"source_id": sid}, {"$set": {"checked_at": utc_now(), "weather": {
        "temperature_2m": 29.0, "dew_point_2m": 21.0, "apparent_temperature": 32.0, "relative_humidity_2m": 60}}}, upsert=True)
    r = rp.build_post_run(conn, "fixture", sid, False)
    assert r["heat"]["hot"] and r["heat"]["say"] == "29°C, dew point 21°C"
    cond = next(c for c in run_checks.build(conn, "fixture", r) if c["id"] == "conditions")
    assert "warm and humid" in cond["say"]
    r["decoupling"].update(eligible=True, decoupling_pct=8.0)
    drift = next(c for c in run_checks.build(conn, "fixture", r) if c["id"] == "drift")
    assert drift["verdict"] == "good" and "warm, humid" in drift["say"]  # heat loosens the bars: 8% is fine when hot
    for pct, want in ((11.0, "ok"), (14.0, "low")):  # ...but they don't vanish
        r["decoupling"].update(decoupling_pct=pct)
        assert next(c for c in run_checks.build(conn, "fixture", r) if c["id"] == "drift")["verdict"] == want
    r["heat"] = None
    r["decoupling"].update(decoupling_pct=11.0)
    assert next(c for c in run_checks.build(conn, "fixture", r) if c["id"] == "drift")["verdict"] == "low"
    assert weather.heat({"temperature_2m": 18.0, "dew_point_2m": 9.0})["hot"] is False


def strain_runs(today, recent_hr, recent_cad, recent_load=60.0):
    """4 weeks of steady runs at 5:30/km, 150 bpm, 170 spm, then a last week with the given heart rate and cadence."""
    out = []
    for k, day in enumerate(range(33, -1, -1)):
        if day % 2:
            continue
        d = today - timedelta(days=day)
        recent = day <= 6
        out.append({"id": k, "source_id": f"s{k}", "source": "x", "local_date": d.isoformat(), "distance_m": 8000.0, "moving_s": 2640.0,
                    "elapsed_s": 2640.0, "avg_hr": recent_hr if recent else 150.0, "avg_cadence_spm": recent_cad if recent else 170.0,
                    "start_utc": f"{d.isoformat()}T06:00:00Z", "load": recent_load if recent else 60.0})
    return out


def test_strain_needs_two_signals(monkeypatch):
    from sidekick import strain
    today = date(2026, 10, 5)
    monkeypatch.setattr(strain.rp, "hr_zones", lambda conn: None)
    monkeypatch.setattr("sidekick.readiness.training_load", lambda conn, s, at, z: {"ratio": 1.0})
    monkeypatch.setattr("sidekick.readiness.moment", lambda conn, d: None)
    monkeypatch.setattr("sidekick.readiness.run_load", lambda conn, a, floors: a["load"])
    monkeypatch.setattr(strain.wx, "unusually_hot", lambda conn: set())

    class C:
        class _C:
            def find_one(self, *a, **k):
                return None
        run_intent = activity_effort = _C()
    for hr, cad, want in ((157.0, 170.0, None), (157.0, 166.0, {"heart_rate", "cadence"})):
        monkeypatch.setattr(strain.rp, "activities", lambda conn, s, a, b, hr=hr, cad=cad: strain_runs(today, hr, cad))
        out = strain.build(C(), "x", today)
        assert (out and {s["id"] for s in out["signals"]}) == (want or None)  # one signal alone is never a warning
    assert "Consider an easier day" in out["text"] and "injur" not in out["text"].lower()


def test_trends_leave_out_only_runs_hotter_than_your_usual():
    from sidekick import weather
    from sidekick.db import connect, user_db_name
    conn = connect(user_db_name(33, "fixture"))
    conn.run_weather.drop()
    for i, dew in enumerate([19, 20, 19, 21, 20, 19, 25]):  # a humid summer: 19–21 is normal here, 25 isn't
        conn.run_weather.insert_one({"source_id": f"r{i}", "checked_at": utc_now(), "weather": {"temperature_2m": 27.0, "dew_point_2m": float(dew)}})
    assert weather.unusually_hot(conn) == {"r6"}


def test_a_very_long_run_with_thinned_samples_keeps_its_analysis():
    # 6 hours at 12-second spacing (Garmin thins long runs out): still moving time, not one long pause
    t = [float(x) for x in range(0, 6 * 3600, 12)]
    s = Samples(t, [140.0] * len(t), [2.8] * len(t), [2.8 * x for x in t], [10.0] * len(t), [168.0] * len(t))
    assert sum(rn._weights(s)) > 0.99 * t[-1]
    assert rn.decoupling(s, [], 2.8 * t[-1], 20.0).get("decoupling_pct") is not None


def test_the_load_ratio_doesnt_drift_through_the_day(monkeypatch):
    from sidekick import readiness as rd
    morning_at = datetime(2026, 10, 2, 5, tzinfo=timezone.utc)
    evening_at = datetime(2026, 10, 2, 18, tzinfo=timezone.utc)
    runs = daily(morning_at.replace(hour=4), n=40, hours=0)
    monkeypatch.setattr(rd, "run_load", lambda conn, a, floors: a["load"])
    monkeypatch.setattr(rd.rp, "get_setting", lambda conn, k, d: d)
    monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b: runs)
    r1 = rd.training_load(None, "x", morning_at, None)["ratio"]
    r2 = rd.training_load(None, "x", evening_at, None)["ratio"]
    assert abs(r1 - r2) < 1e-9  # same runs, same day: the same ratio morning and evening


def test_sessions_expire_logout_works_and_deleted_users_can_be_reinvited(tmp_path):
    from sidekick import accounts
    from sidekick.auth import create_token
    from test_multiuser import client
    c = client(tmp_path)
    tok = create_token(tmp_path, "t")
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/v1/me", headers=h).status_code == 200
    assert c.post("/v1/auth/logout", headers=h).json() == {"signed_out": True}
    assert c.get("/v1/me", headers=h).status_code == 401  # signed out on the server, not just on the phone
    tok2 = create_token(tmp_path, "t2")
    a = accounts.app_db()
    a.sessions.update_one({"token_sha256": accounts._hash(tok2)}, {"$set": {"last_used_at": "2026-01-01T00:00:00Z"}})
    assert c.get("/v1/me", headers={"Authorization": f"Bearer {tok2}"}).status_code == 401  # idle too long
    accounts.add_invite(a, "gone@example.com")
    a.invites.update_one({"email": "gone@example.com"}, {"$set": {"used_at": "2026-09-01T00:00:00Z"}})  # used, then the user was deleted
    accounts.add_invite(a, "gone@example.com")
    assert a.invites.find_one({"email": "gone@example.com"})["used_at"] is None


def test_rate_limit(tmp_path, monkeypatch):
    from sidekick.auth import create_token
    from test_multiuser import client
    monkeypatch.setenv("RSK_RATE_LIMIT", "5")
    c = client(tmp_path)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    codes = [c.get("/v1/me", headers=h).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_a_temperate_summer_stays_in_the_trends():
    from sidekick import weather
    from sidekick.db import connect, user_db_name
    conn = connect(user_db_name(33, "fixture"))
    conn.run_weather.drop()
    for i, dew in enumerate([8, 9, 10, 9, 11, 8, 15]):  # 15 °C is warm for this runner but not humid enough to matter
        conn.run_weather.insert_one({"source_id": f"r{i}", "checked_at": utc_now(), "weather": {"temperature_2m": 24.0, "dew_point_2m": float(dew)}})
    assert weather.unusually_hot(conn) == set()


def test_weather_switch_and_catch_up():
    from sidekick import weather
    conn = synced()
    conn.run_weather.drop()
    runs = rp.activities(conn, "fixture", "2000-01-01", "9999-12-31")
    for a in runs:  # give every run a start position
        conn.raw_payload.update_one({"kind": "activity_summary", "source_key": a["source_id"]},
                                    {"$set": {"payload.startLatitude": 32.1, "payload.startLongitude": 34.8}}, upsert=True)
    calls = []

    class R:
        def __init__(self, day):
            self.day = day

        def raise_for_status(self):
            pass

        def json(self):
            return {"hourly": {"time": [f"{self.day}T{h:02d}:00" for h in range(24)], "temperature_2m": [20.0] * 24,
                               "dew_point_2m": [12.0] * 24}}

    def fetch(url, params, timeout):
        calls.append(params)
        return R(params["start_date"])
    from sidekick.db import set_setting
    set_setting(conn, "weather_enabled", False)
    assert weather.for_new_runs(conn, "fixture", [runs[-1]["source_id"]], fetch) == [] and not calls  # off: nothing is sent
    assert weather.for_run(conn, runs[-1], fetch) is None and not calls
    set_setting(conn, "weather_enabled", True)
    old = runs[0]["source_id"]  # a sync's own runs come first, however old
    got = weather.for_new_runs(conn, "fixture", [old], fetch)
    assert got[0] == old and len(got) == len(calls) <= weather.SYNC_LOOKUPS
    recent = {a["source_id"] for a in runs if a["local_date"] >= (date.today() - timedelta(days=weather.CATCH_UP_DAYS)).isoformat()}
    assert recent <= set(got) or len(got) == weather.SYNC_LOOKUPS  # recent runs without weather are caught up too
    calls.clear()
    assert weather.for_new_runs(conn, "fixture", [old], fetch) == [] and not calls  # nothing asked twice


def test_an_out_and_back_on_a_hill_isnt_read_as_a_fade(monkeypatch):
    from sidekick import run_checks
    monkeypatch.setattr(rp, "hr_zones", lambda conn: None)
    up = [{"idx": i, "distance_m": 1000.0, "pace_s_per_km": 330.0, "gap_pace_s_per_km": 330.0, "complete": True,
           "elevation_gain_m": 2.0, "elevation_loss_m": 25.0} for i in range(4)]  # down the hill and easy...
    back = [{"idx": i + 4, "distance_m": 1000.0, "pace_s_per_km": 360.0, "gap_pace_s_per_km": 350.0, "complete": True,
             "elevation_gain_m": 25.0, "elevation_loss_m": 2.0} for i in range(4)]  # ...then back up at the same heart rate
    assert rn.uneven_halves(up + back) is not None
    report = {"splits": up + back, "activity": {"source_id": "x", "elevation_gain_m": 108.0}, "intent": {}}
    pacing = next(c for c in run_checks.build(None, "fixture", report) if c["id"] == "pacing")
    assert pacing["verdict"] == "info" and "not comparable" in pacing["say"]
    flat = [{**s, "elevation_gain_m": 3.0, "elevation_loss_m": 3.0} for s in up + back]
    assert rn.uneven_halves(flat) is None
    assert next(c for c in run_checks.build(None, "fixture", {**report, "splits": flat}) if c["id"] == "pacing")["verdict"] == "low"


def test_a_hot_day_loosens_the_pacing_bar(monkeypatch):
    from sidekick import run_checks
    monkeypatch.setattr(rp, "hr_zones", lambda conn: None)
    sp = [{"idx": i, "distance_m": 1000.0, "pace_s_per_km": 330.0 + (20 if i >= 2 else 0), "complete": True} for i in range(4)]
    rep = {"splits": sp, "activity": {"source_id": "x"}, "intent": {}}
    verdict = lambda r: next(c for c in run_checks.build(None, "fixture", r) if c["id"] == "pacing")["verdict"]  # noqa: E731
    assert verdict(rep) == "low" and verdict({**rep, "heat": {"hot": True, "say": "30°C"}}) == "ok"
    sp2 = [{**s, "pace_s_per_km": 330.0 + (30 if s["idx"] >= 2 else 0)} for s in sp]
    assert verdict({**rep, "splits": sp2, "heat": {"hot": True, "say": "30°C"}}) == "low"  # looser, not gone


def test_weekly_long_run_leftover_is_routine_an_unusual_one_isnt(monkeypatch):
    from sidekick import readiness as rd
    at = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(rd, "run_load", lambda conn, a, floors: a["load"])
    monkeypatch.setattr(rd.rp, "get_setting", lambda conn, k, d: d)
    weekly = {k: 180.0 for k in range(1, 61, 7)}  # a big run every week, yesterday included
    monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b: daily(at, extra=weekly))
    tl = rd.training_load(None, "x", at, None)
    assert tl["fatigue"] > 0.3 and tl["routine"]
    monkeypatch.setattr(rd.rp, "activities", lambda conn, s, a, b: daily(at, extra={1: 300.0}))
    assert not rd.training_load(None, "x", at, None)["routine"]


def test_strain_leaves_hard_sessions_out_of_felt_harder_and_reads_identical_days_as_monotony(monkeypatch):
    from sidekick import strain
    today = date(2026, 10, 5)
    monkeypatch.setattr(strain.rp, "hr_zones", lambda conn: {"floors": [100, 120, 140, 160, 175]})
    monkeypatch.setattr("sidekick.readiness.training_load", lambda conn, s, at, z: {"ratio": 1.0})
    monkeypatch.setattr("sidekick.readiness.moment", lambda conn, d: None)
    monkeypatch.setattr("sidekick.focus.zone_shares", lambda conn, a, f: {"hard": 0.05, "easy": 0.9})
    monkeypatch.setattr(strain.wx, "unusually_hot", lambda conn: set())

    def conn_with(kind):
        class C:
            class _I:
                def find_one(self, *a, **k):
                    return {"kind": kind, "effort": "hard"}
            run_intent = _I()

            class _E:
                def find_one(self, *a, **k):
                    return None
            activity_effort = _E()
        return C()
    # Every day the same load this week, heavier than before: monotony with no spread at all
    runs = [{"id": k, "source_id": f"s{k}", "local_date": (today - timedelta(days=d)).isoformat(), "distance_m": 8000.0, "moving_s": 2640.0,
             "elapsed_s": 2640.0, "avg_hr": 150.0, "avg_cadence_spm": 170.0, "load": 80.0 if d <= 6 else 30.0}
            for k, d in enumerate(range(33, -1, -1)) if d <= 6 or d % 3 == 0]
    monkeypatch.setattr(strain.rp, "activities", lambda conn, s, a, b: runs)
    monkeypatch.setattr("sidekick.readiness.run_load", lambda conn, a, floors: a["load"])
    ids = {s["id"] for s in strain.build(conn_with("easy"), "x", today)["signals"]}
    assert ids == {"monotony", "felt"}
    assert strain.build(conn_with("tempo"), "x", today) is None  # tempo is meant to feel hard: only monotony is left


def test_junk_tokens_dont_get_a_bucket_of_their_own(tmp_path, monkeypatch):
    from sidekick.auth import create_token
    from test_multiuser import client
    monkeypatch.setenv("RSK_RATE_LIMIT", "100")
    c = client(tmp_path)
    good = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    codes = [c.get("/v1/me", headers={"Authorization": f"Bearer junk{i}"}).status_code for i in range(10)]
    assert codes == [401] * 10
    assert c.get("/v1/me", headers=good).status_code == 429  # 10 rejected tries from this address: it waits, whatever the token


def test_the_decision_says_when_reported_illness_is_applied(monkeypatch):
    from sidekick import decide as dc
    monkeypatch.setattr(dc.rd, "build", lambda conn, s, d, m: {"status": "ok", "score": 80})
    monkeypatch.setattr(dc.rd, "next_run", lambda *a, **k: None)
    monkeypatch.setattr(dc.race, "status", lambda conn, d: None)
    for rule, want in (("R0", True), ("R1", False)):
        out = dc.decide(None, "x", date(2026, 10, 5), {"recommendation": {"rule_id": rule, "state": "normal"}})
        assert out["unwell_applied"] is want and (out["allows"] == "rest") is want


def test_a_disabled_account_is_signed_out_refused_and_not_synced(tmp_path):
    from sidekick import accounts
    a = accounts.app_db()
    owner = accounts.ensure_owner(a)
    accounts.add_invite(a, "member@example.com")
    claims = {"email": "member@example.com", "email_verified": True, "sub": "g-member", "name": "M"}
    u = accounts.sign_in_with_google(a, claims)
    tok = accounts.create_session(a, u["id"], "phone")
    assert accounts.verify_session(a, tok) is not None
    accounts.set_disabled(a, u["id"], True)
    assert accounts.verify_session(a, tok) is None  # signed out now
    import pytest
    with pytest.raises(accounts.NotInvited, match="disabled"):
        accounts.sign_in_with_google(a, claims)
    assert next(x for x in accounts.list_users(a) if x["id"] == u["id"])["disabled_at"]
    with pytest.raises(ValueError):
        accounts.set_disabled(a, owner["id"], True)  # never the owner
    accounts.set_disabled(a, u["id"], False)
    assert accounts.sign_in_with_google(a, claims)["id"] == u["id"]
    assert accounts.find_user(a, "MEMBER@example.com")["id"] == u["id"] and accounts.find_user(a, str(u["id"]))


def test_connecting_garmin_from_a_ticket(tmp_path):
    from sidekick import garmin_link as gl

    class FakeClient:
        def __init__(self, owner):
            self.owner = owner

        def _exchange_service_ticket(self, ticket, service_url):
            assert service_url == gl.SSO_EMBED
            if ticket == "ST-expired-0000":
                raise RuntimeError("DI token exchange failed")
            self.owner.ticket = ticket

        def dump(self, path):
            (Path(path) / gl.TOKEN_FILE).write_text('{"di_token": "t"}')

    profiles = {"ST-mine-00000001": 111, "ST-theirs-0000001": 222}
    last = {}

    class FakeGarmin:
        def __init__(self):
            self.client, self.profile_id, self.display_name = FakeClient(self), None, None

        def login(self, tokenstore):
            self.profile_id = profiles[last["ticket"]]

    def factory():
        g = FakeGarmin()
        orig = g.client._exchange_service_ticket
        g.client._exchange_service_ticket = lambda t, service_url: (last.update(ticket=t), orig(t, service_url))
        return g
    from pathlib import Path
    users = tmp_path / "users"
    mine, theirs = users / "1" / "garmin_tokens", users / "2" / "garmin_tokens"
    assert not gl.linked(mine)
    assert gl.link(mine, "ST-mine-00000001", users, 1, factory)["profile_id"] == 111
    assert gl.linked(mine) and gl.profile_of(mine) == 111
    import pytest
    with pytest.raises(gl.LinkError, match="another Runner Sidekick account"):
        gl.link(theirs, "ST-mine-00000001", users, 2, factory)  # one Garmin account, one app user
    assert not gl.linked(theirs)
    with pytest.raises(gl.LinkError, match="expired"):
        gl.link(mine, "ST-expired-0000", users, 1, factory)
    assert gl.linked(mine) and gl.profile_of(mine) == 111  # a failed relink never breaks the working one
    assert not list((users / "1").glob(".garmin-link-*"))  # no temporary folders left behind
    with pytest.raises(gl.LinkError, match="different Garmin account"):
        gl.link(mine, "ST-theirs-0000001", users, 1, factory, expected_profile=111)  # same app user, other person's Garmin
    assert gl.profile_of(mine) == 111
    assert gl.unlink(mine) and not gl.linked(mine)


def test_one_weak_part_floors_the_final_score_with_other_parts_missing(monkeypatch):
    from sidekick import readiness as rd
    monkeypatch.setattr(rd, "training_load", lambda *a, **k: None)
    monkeypatch.setattr(rd, "garmin_check", lambda *a, **k: None)
    monkeypatch.setattr(rd, "moment", lambda conn, d: None)
    monkeypatch.setattr(rd.rp, "hr_zones", lambda conn: None)
    monkeypatch.setattr(rd, "current", lambda f, d: ((f or {}).get("v"), None))
    monkeypatch.setattr(rd, "usual", lambda f, d: ((f or {}).get("base"), "your usual"))
    morning = {"recommendation": {"rule_id": "R1"}, "findings": [
        {"metric": "hrv_overnight_avg", "v": 30.0, "base": 60.0},  # 50% below usual: 0 points
        {"metric": "sleep_duration", "v": 6.0 * 3600}]}           # 6 h: 60 points, not weak
    out = rd.build(None, "x", date(2026, 10, 5), morning)
    assert out["score"] == rd.SINGLE_SIGNAL_FLOOR and out["floored_by"] == "hrv"  # easy, not rest
    morning["findings"].append({"metric": "resting_hr", "v": 60.0, "base": 50.0})  # a second weak part: no floor
    assert rd.build(None, "x", date(2026, 10, 5), morning)["score"] < rd.SINGLE_SIGNAL_FLOOR


def test_heart_rate_has_to_cover_most_of_the_whole_run(monkeypatch):
    from sidekick import focus
    t = [float(x) for x in range(1000)]
    hr = [170.0 if x < 600 else None for x in range(1000)]  # 600 s of valid heart rate in a 1000-s run
    s = Samples(t, hr, [3.0] * 1000, [3.0 * x for x in t], [10.0] * 1000, [170.0] * 1000)
    monkeypatch.setattr(focus.rp, "samples_for", lambda conn, i: s)
    a = {"id": 1, "source_id": "a", "local_date": "2026-10-01", "distance_m": 3000.0, "moving_s": 1000.0}
    assert focus.zone_shares(None, a, [100, 120, 140, 155, 165]) is None  # 60% isn't "most of the run"
    s.hr[:] = [170.0 if x < 800 else None for x in range(1000)]
    assert focus.zone_shares(None, a, [100, 120, 140, 155, 165]) is not None


def test_trophies_combine_garmin_records_with_our_bests_and_age_compare():
    from sidekick import trophies
    from sidekick.db import set_setting
    conn = synced()
    set_setting(conn, "garmin_records", {"records": [{"type": 3, "value": 3000.0, "activity_id": None, "date": "2025-01-01"},  # slower than ours
                                                     {"type": 4, "value": 2700.0, "activity_id": "fx-run-2026-09-05", "date": "2026-09-05"},
                                                     {"type": 99, "value": 1.0, "activity_id": None, "date": None}]}, )
    out = trophies.build(conn, "fixture", ANCHOR)
    items = {i["id"]: i for g in out["groups"] for i in g["items"]}
    assert items["5k"]["source"].startswith("the fastest stretch") and items["5k"]["seconds"] < 3000  # the faster of the two
    assert items["10k"]["seconds"] == 2700.0 and items["10k"]["source_id"] == "fx-run-2026-09-05"  # Garmin's, linked to the run
    assert "age grade" in items["10k"]["comparison"]["headline"]
    assert items["longest"]["source"] == "your runs" and items["week"]["metres"] > 0
    assert items["resting_hr"]["comparison"]["headline"].startswith("Your usual")
    assert "1k" in items and items["1k"]["comparison"] is None  # no age standard for 1 km: no comparison made up
    set_setting(conn, "profile_sex", None)
    conn.user_settings.delete_many({"key": {"$in": ["profile_sex", "source_profile"]}})
    assert all(i.get("comparison") is None for g in trophies.build(conn, "fixture", ANCHOR)["groups"] for i in g["items"])  # no sex: none


def test_a_sync_tapped_during_another_waits_for_it_then_syncs(tmp_path, monkeypatch):
    import threading
    import time as _t
    from sidekick import api as api_mod
    from sidekick.auth import create_token
    from sidekick.db import connect, user_db_name
    from sidekick.sync import release_lease, take_lease
    from test_multiuser import client
    monkeypatch.setattr(api_mod, "SYNC_WAIT_S", 0.1)
    c = client(tmp_path)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    conn = connect(user_db_name(1, "fixture"))
    lease = take_lease(conn, datetime.now(timezone.utc))  # the hourly job is mid-sync
    assert lease
    assert c.post("/v1/sync", headers=h).json()["started"] is True
    _t.sleep(0.5)
    assert c.get("/v1/status", headers=h).json()["sync_running"]  # waiting for it, not ended empty
    assert conn.sync_job.count_documents({}) == 0
    release_lease(conn, lease)
    for _ in range(200):
        if not c.get("/v1/status", headers=h).json()["sync_running"]:
            break
        _t.sleep(0.05)
    assert conn.sync_job.count_documents({"outcome": "ok"}) == 1  # then it synced itself


def test_a_run_sets_a_record_only_by_beating_an_earlier_best():
    from sidekick import trophies
    from sidekick.db import set_setting
    conn = synced()
    conn.user_settings.delete_many({"key": "garmin_records"})
    pg = trophies.progressions(conn, "fixture", ANCHOR)
    sets = trophies.records_set(conn, "fixture", ANCHOR)
    first = rp.activities(conn, "fixture", "0000-01-01", ANCHOR.isoformat())[0]["source_id"]
    assert first not in sets  # the first run in the history isn't a "new best" of everything
    for rid, pts in pg.items():
        vals = [p["value"] for p in pts]
        assert vals == sorted(vals, reverse=rid in trophies.LOWER_IS_BETTER) and len(set(vals)) == len(vals)  # each point improves
    assert all(r["id"] in trophies.RUN_RECORDS for rs in sets.values() for r in rs)
    # An older Garmin all-time record is the bar: nothing in the synced history beats a 15:00 5 km
    set_setting(conn, "garmin_records", {"records": [{"type": 3, "value": 900.0, "activity_id": None, "date": "2020-01-01"}]})
    assert not any(r["id"] == "5k" for rs in trophies.records_set(conn, "fixture", ANCHOR).values() for r in rs)
    item = next(i for g in trophies.build(conn, "fixture", ANCHOR)["groups"] for i in g["items"] if i["id"] == "5k")
    assert item["history"][0]["garmin"] and item["lower_is_better"]
    # Garmin's count of a run we measured too: one point for that run, not two
    conn.user_settings.delete_many({"key": "garmin_records"})
    last = trophies.progressions(conn, "fixture", ANCHOR)["1k"][-1]
    set_setting(conn, "garmin_records", {"records": [{"type": 1, "value": last["value"] - 0.4, "activity_id": last["source_id"], "date": last["date"]}]})
    pts = trophies.progressions(conn, "fixture", ANCHOR)["1k"]
    assert [p["source_id"] for p in pts].count(last["source_id"]) == 1 and pts[-1]["value"] == last["value"] - 0.4


def test_cardio_fitness_keeps_its_evidence_apart(tmp_path):
    from sidekick import cardio
    from sidekick.auth import create_token
    from test_multiuser import client
    # Jackson 1990, BMI model: a 43-year-old man, BMI 23.1, activity 7 → 56.363 + 13.447 − 16.383 − 17.4 + 10.987
    assert round(56.363 + 1.921 * 7 - 0.381 * 43 - 0.754 * (74 / 1.79 ** 2) + 10.987) == 47
    assert abs(cardio.vdot(5000, 20 * 60 + 0) - 49.8) < 0.5  # Daniels' table: a 20:00 5 km is about VDOT 50
    conn = synced()
    assert set(cardio.build(conn, "fixture", ANCHOR)["runs"]["left_out"]) >= {"weather unknown"}  # unknown isn't "cool"
    for a in rp.activities(conn, "fixture", "0000-01-01", ANCHOR.isoformat()):
        conn.run_weather.update_one({"source_id": a["source_id"]}, {"$set": {"checked_at": utc_now(), "weather": {
            "temperature_2m": 18.0, "dew_point_2m": 10.0, "apparent_temperature": 18.0}}}, upsert=True)
    out = cardio.build(conn, "fixture", ANCHOR)
    assert out["questionnaire"]["status"] == "needs_input"  # no activity answer yet: no made-up baseline
    assert out["runs"]["status"] == "ok" and out["runs"]["spread"][0] <= out["runs"]["value"] <= out["runs"]["spread"][1]
    assert sum(out["runs"]["left_out"].values()) > 0 and all(out["runs"]["left_out"])  # every left-out run has a reason
    assert not any("VDOT" in n for n in out["notes"])  # performance is never set against the VO2 max estimates
    assert "comparison" in out["runs"] and "for men aged" in out["runs"]["comparison"]["headline"]
    assert "comparison" not in out["performance"]  # VDOT isn't placed among VO2 max norms
    # Answers are kept with the day they were given, and can be cleared
    c = client(tmp_path)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    s = c.put("/v1/settings", headers=h, json={"activity_par": 6, "hr_max": 186}).json()
    assert s["activity_par"] == 6 and s["activity_par_at"] and s["hr_max"] == 186
    assert c.get("/v1/cardio", headers=h).json()["hr_max"]["source"].startswith("set by you")
    assert c.put("/v1/settings", headers=h, json={"hr_max": None}).json()["hr_max"] is None
    assert c.put("/v1/settings", headers=h, json={"activity_par": 9}).status_code == 422


def test_cardio_inputs_are_robust_to_spikes_zeros_and_stale_readings(monkeypatch):
    from sidekick import cardio
    from sidekick.connectors.base import Samples, valid_hr
    from sidekick.db import set_setting
    # A spike: 150 bpm for most of a minute, then 5 dense seconds at 220 → about 156, not 210
    t = [float(x) for x in range(55)] + [55 + 0.1 * k for k in range(50)] + [60.0 + x for x in range(5)]
    hr = [150.0] * 55 + [220.0] * 50 + [150.0] * 5
    s = Samples(t, hr, [3.0] * len(t), [3.0 * x for x in t], [10.0] * len(t), [170.0] * len(t))
    assert 150 <= cardio.sustained_max(s) < 160
    # Six readings around a long gap aren't a sustained minute
    gap = Samples([0.0, 1, 2, 50, 51, 52], [180.0] * 6, [3.0] * 6, [0.0] * 6, [10.0] * 6, [170.0] * 6)
    assert cardio.sustained_max(gap) is None
    # Zeros from the strap are gaps, everywhere samples are read
    assert valid_hr([150, 0, None, 255, 160]) == [150, None, None, None, 160]
    assert Samples.from_json({"t": [0, 1], "hr": [0, 150], "speed": [3, 3], "dist": [0, 3], "elev": [1, 1], "cad": [170, 170]}).hr == [None, 150]
    # Garmin's value: the newest reading, not any older one in the series
    conn = synced()
    conn.daily_observation.delete_many({"metric": "garmin_vo2max_running"})
    conn.daily_observation.insert_one({"source": "fixture", "metric": "garmin_vo2max_running", "state": "measured",
                                       "local_date": (ANCHOR - timedelta(days=30)).isoformat(), "value": 40.0})
    set_setting(conn, "garmin_fitness", {"vo2max": {"value": 50.0, "date": ANCHOR.isoformat()}})
    assert cardio.build(conn, "fixture", ANCHOR)["garmin"]["value"] == 50
    # The questionnaire estimate through build(), with its own inputs
    set_setting(conn, "activity_par", 7)
    set_setting(conn, "profile_weight_kg", 74.0)
    set_setting(conn, "profile_height_cm", 179.0)
    q = cardio.build(conn, "fixture", ANCHOR)["questionnaire"]
    age = q["detail"].split("age (")[1].split(")")[0]
    want = 56.363 + 1.921 * 7 - 0.381 * int(age) - 0.754 * (74 / 1.79 ** 2) + 10.987
    assert q["status"] == "ok" and q["value"] == round(want)
    # Notes never diagnose a cause
    assert not any("usual cause" in n for n in cardio.build(conn, "fixture", ANCHOR)["notes"])


def test_cardio_flat_means_flat_and_sensitivity_keeps_the_same_runs(monkeypatch):
    from sidekick import cardio
    conn = synced()
    a = dict(next(x for x in reversed(rp.activities(conn, "fixture", "0000-01-01", ANCHOR.isoformat()))
                  if (rp.run_analysis(conn, x).get("classification") or {}).get("kind") == "steady"))
    conn.run_weather.update_one({"source_id": a["source_id"]}, {"$set": {"checked_at": utc_now(), "weather": {
        "temperature_2m": 18.0, "dew_point_2m": 10.0, "apparent_temperature": 18.0}}}, upsert=True)
    down = {**a, "elevation_gain_m": 0.0, "elevation_loss_m": 216.0, "distance_m": 7200.0}  # a steady 3% descent
    assert cardio.run_estimate(conn, down, 50, 185)[1].startswith("hilly")
    assert cardio.run_estimate(conn, {**a, "elevation_loss_m": None}, 50, 185)[1] == "elevation not recorded"
    # Sensitivity: the same observation, only the maximum changed, and a lower maximum gives a lower estimate
    e = {"vo2": 40.0, "hr": 150.0, "hr_rest": 50.0}
    assert cardio.with_hr_max(e, 175) < cardio.with_hr_max(e, 180)


def test_training_numbers_known_answers():
    from sidekick import numbers
    from sidekick.connectors.base import Samples
    # A climb: 5 minutes rising 60 m over 1200 m (5%), on the flat before and after → VAM 720 m/h
    t, d, e = [], [], []
    for x in range(0, 1500, 2):
        t.append(float(x))
        d.append(4.0 * x)
        e.append(10.0 + (0 if x < 600 else min(60.0, (x - 600) / 300 * 60)))
    s = Samples(t, [150.0] * len(t), [4.0] * len(t), d, e, [170.0] * len(t))
    c = numbers.best_climb(s)
    assert c and 700 <= c["vam"] <= 740 and c["gain_m"] >= 55
    flat = Samples(t, [150.0] * len(t), [4.0] * len(t), d, [10.0] * len(t), [170.0] * len(t))
    assert numbers.best_climb(flat) is None
    # Intervals: 2 min fast ending at 175 bpm, then a slow minute where it falls to 145 → a 30 bpm drop each
    t, hr, v = [], [], []
    x = 0.0
    for rep in range(3):
        for k in range(120):
            t.append(x); hr.append(150 + 25 * k / 119); v.append(4.5); x += 1
        for k in range(120):
            t.append(x); hr.append(175 - min(30, 30 * k / 60)); v.append(2.5); x += 1
    drops = numbers.recovery_drops(Samples(t, hr, v, [0.0] * len(t), [10.0] * len(t), [170.0] * len(t)), 170)
    assert len(drops) == 3 and all(28 <= dd["drop"] <= 32 for dd in drops) and all(dd["recovery_speed"] > 1.7 for dd in drops)
    # Form bands, and Garmin's threshold speed comes in tenths of a metre per second
    assert next(b for b in numbers.FORM_BANDS if b[0] is None or -35 >= b[0])[1] == "Recent load well above your usual"
    assert numbers.pace(3.083) == rp.fmt_pace(1000 / 3.083)
    conn = synced()
    items = {i["id"]: i for i in numbers.build(conn, "fixture", ANCHOR)["items"]}
    assert set(items) == {"threshold", "form", "predictions", "recovery", "climbing"}
    assert all(i["status"] != "ok" or (i["value"] and i["series"]) for i in items.values())


def test_training_numbers_dont_flatter_or_invent(monkeypatch):
    from sidekick import numbers
    from sidekick.connectors.base import Samples
    # A poor recovery is kept: drops of 30, 30 and 2 bpm all count
    t, hr, v = [], [], []
    x = 0.0
    for fall in (30, 30, 2):
        for k in range(120):
            t.append(x); hr.append(150 + 25 * k / 119); v.append(4.5); x += 1
        for k in range(120):
            t.append(x); hr.append(175 - min(fall, fall * k / 60)); v.append(2.5); x += 1
    drops = [d["drop"] for d in numbers.recovery_drops(Samples(t, hr, v, [0.0] * len(t), [10.0] * len(t), [170.0] * len(t)), 170)]
    assert len(drops) == 3 and min(drops) < 5
    # No climb across a 301-second hole in the recording
    t, d, e = [], [], []
    for x in list(range(0, 600, 2)) + list(range(901, 1500, 2)):
        t.append(float(x)); d.append(4.0 * x); e.append(10.0 if x < 600 else 70.0)
    assert numbers.best_climb(Samples(t, [150.0] * len(t), [4.0] * len(t), d, e, [170.0] * len(t))) is None
    # An old climb isn't called "best in 90 days"
    conn = synced()
    old = rp.activities(conn, "fixture", "0000-01-01", ANCHOR.isoformat())[0]
    monkeypatch.setattr(numbers, "climb_of", lambda c, a: {"vam": 700, "gain_m": 40, "minutes": 4, "grade": 4.0} if a["id"] == old["id"] else None)
    later = date.fromisoformat(old["local_date"]) + timedelta(days=150)
    cl = numbers.climbing(conn, "fixture", later)
    assert cl["status"] == "ok" and "90 days" in cl["headline"] and cl["headline"].startswith("best in the last year")
    # 30 days without running: not "fresh, ready to race", but a break
    f = numbers.form(conn, "fixture", ANCHOR + timedelta(days=30))
    assert f["headline"] == "Little recent training" and "race" not in (f["detail"] + f["headline"]).lower()
    assert all("race" not in b[2].lower() and "build" not in b[2].lower() for b in numbers.FORM_BANDS)
