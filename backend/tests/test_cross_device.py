"""Pacing windows and cross-device regressions (2026-11-15 review of an Apple Watch tempo run after Garmin history):
a run's pacing is read in named windows with where a slowdown happened, drift reads as aerobic drift only when the
effort held, and nothing is compared in watts, HRV or a watch's VO2 max between Garmin and Apple Watch."""
from datetime import date, timedelta

from sidekick import progress, run_checks, run_export
from sidekick import reports as rp
from sidekick.analytics import running as rn
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name

from test_apple import ANCHOR, TODAY, app, run

# The 15 Nov 2026 Apple Watch tempo: hill-adjusted pace of its 7 complete km (s/km). A quick first 3 km, then steady.
NOV15_GAP = [333, 330, 335, 350, 353, 347, 346]


def splits(gap, raw=None, hr=None):
    raw = raw or gap
    return [{"idx": i, "pace_s_per_km": r, "gap_pace_s_per_km": g, "complete": True, "distance_m": 1000.0,
             "avg_hr": (hr or [155] * len(gap))[i]} for i, (g, r) in enumerate(zip(gap, raw))]


def drift(sp1, sp2, pace_dc=1.9, power=None):
    out = {"eligible": True, "decoupling_pct": pace_dc, "first_half": {"mean_speed_mps": 1000 / sp1, "mean_hr": 156},
           "second_half": {"mean_speed_mps": 1000 / sp2, "mean_hr": 158}}
    out.update(rn.suitability(100 * (1000 / sp2 - 1000 / sp1) / (1000 / sp1), power, {"kind": "steady"}, pace_dc, None))
    return out


def checks(report):
    return {c["id"]: c for c in run_checks.build(connect(user_db_name(1, "fixture")), "fixture", report)}


def pacing(report):
    return checks(report)["pacing"]


def test_full_run_slowdown_with_a_steady_drift_window_is_explained_not_failed():
    # (2) Halves +16 s/km on the whole run, 5:45 → 5:46 after the warm-up: the start, not a fade
    sh = rn.pacing_shape(NOV15_GAP)
    assert sh["where"] == "opening" and sh["laps"] == 2 and round(sh["fade"]) == 16
    rep = {"splits": splits(NOV15_GAP), "intent": {"kind": "tempo", "effort": "moderate", "feel": "great"},
           "decoupling": drift(345, 346), "activity": {"source_id": "x"}}
    c = pacing(rep)
    assert c["verdict"] == "ok" and "Quick first 2 km" in c["say"] and "after the first 10 minutes it held (5:45 /km → 5:46 /km)" in c["say"]
    story = rn.run_story([rn.Split(i, 1000.0, p, p, 155.0, 0.0, float(p), True) for i, p in enumerate(NOV15_GAP)],
                         [{"gap_pace_s_per_km": p} for p in NOV15_GAP], rp.fmt_pace)
    assert any("were quicker" in x and "held steady" in x for x in story) and not any("faded" in x for x in story)


def test_pacing_verdict_weighs_where_heart_rate_and_how_it_felt():
    late = [330] * 4 + [345, 352, 360]  # steady, then slower at the end: +24 s/km
    rep = {"splits": splits(late), "intent": {"kind": "tempo"}, "activity": {"source_id": "x"}}
    c = pacing(rep)
    assert rn.pacing_shape(late)["where"] == "final" and c["verdict"] == "low" and "at the end" in c["say"]
    # Heart rate fell with the pace: eased off, not faded
    eased = pacing({**rep, "splits": splits(late, hr=[160, 160, 160, 158, 152, 150, 149])})
    assert eased["verdict"] == "ok" and "eased off" in eased["say"]
    # Felt great at a moderate effort supports "ok" only while the slowdown is within twice the bar
    felt = {"kind": "tempo", "effort": "moderate", "feel": "great"}
    assert pacing({**rep, "intent": felt})["verdict"] == "ok"
    much = [330] * 4 + [370, 380, 390]
    assert pacing({**rep, "splits": splits(much), "intent": felt})["verdict"] == "low"


def test_hills_in_raw_splits_dont_read_as_a_fade():
    # (3) Raw km paces swing with the hills; the hill-adjusted ones are even
    raw = [330, 365, 300, 362, 331, 368, 329]
    c = pacing({"splits": splits([331, 333, 330, 334, 331, 332, 330], raw=raw), "activity": {"source_id": "x"}})
    assert c["verdict"] == "good" and c["say"] == "Even all the way"


def test_progressive_run_and_genuine_drift_are_told_apart():
    # (4) A progressive run: the second half 6% faster reads as low drift, so it's flagged, the number kept
    prog = drift(360, 340, pace_dc=-2.5)
    assert prog["suitability"] == "caution" and "progressive" in prog["suitability_why"][0] and prog["decoupling_pct"] == -2.5
    chk = checks({"splits": [], "decoupling": prog, "activity": {"source_id": "x"}})["drift"]
    assert chk["verdict"] == "info" and "interpret with caution" in chk["say"]
    # (9) A steady tempo whose heart rate genuinely drifted: a good measurement, judged as drift
    real = drift(345, 346, pace_dc=8.0)
    assert real["suitability"] == "good"
    chk = checks({"splits": [], "decoupling": real, "activity": {"source_id": "x"}})["drift"]
    assert chk["verdict"] == "ok" and "rose as you went" in chk["say"]


def test_a_short_finishing_sprint_is_neither_a_fade_nor_unsteady():
    # (8) Six even km and a quick last one; a one-minute kick barely moves the drift window's halves
    sprint = [340] * 6 + [312]
    assert rn.pacing_shape(sprint)["where"] is None
    assert pacing({"splits": splits(sprint), "activity": {"source_id": "x"}})["verdict"] == "good"
    assert rn.suitability(1.5, None, {"kind": "steady"}, 2.0, None)["suitability"] == "good"


def test_power_and_pace_drift_disagreeing_is_explained():
    out = rn.suitability(0.3, -2.6, {"kind": "steady"}, 1.9, 3.9)
    assert out["suitability"] == "good" and "fell 3%" in out["power_vs_pace"] and "own estimate" in out["power_vs_pace"]


def mixed_history(tmp_path, dynamics=True, power=True):
    """Garmin's demo history up to ANCHOR, then the account switched to Apple Watch and one similar Apple run."""
    from sidekick.sync import run_sync
    client, h, _ = app(tmp_path, backfill_days=(TODAY - ANCHOR).days + 40)
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    for a in conn.activity.find({}):  # Garmin's own power scale on the earlier runs
        conn.activity.update_one({"_id": a["_id"]}, {"$set": {"garmin_metrics": {**(a.get("garmin_metrics") or {}), "avgPower": 330}}})
    client.put("/v1/settings", json={"watch": "apple"}, headers=h)
    w = run(ANCHOR + timedelta(days=2), "aw1", km=8.0, pace_s=326.0, pause_at=None, hill=False)
    if not power:
        w["series"].pop("power")
    if not dynamics:
        w.pop("dynamics")
    assert client.post("/v1/apple", json={"workouts": [w], "hrv": [
        {"time": f"{(ANCHOR + timedelta(days=2)).isoformat()}T02:{m:02d}:00+03:00", "sdnn_ms": 40.0 + m, "beats": 60} for m in (10, 40)]},
        headers=h).status_code == 200
    return client, h, conn, "apple-aw1"


def test_apple_run_after_garmin_history_compares_nothing_across_watches(tmp_path):
    # (1, 5, 7) Mixed history: power isn't compared in watts, Garmin-only metrics aren't invented, devices are named
    _, _, conn, sid = mixed_history(tmp_path)
    md = run_export.markdown(conn, "fixture", sid, app_version="test")[1]
    sim = md.split("## Similar runs", 1)[1].split("\n## ", 1)[0] if "## Similar runs" in md else ""
    assert sim, "the Apple run should have similar Garmin runs"
    assert "Power: **not comparable**" in sim and " W**" not in sim.split("| Date |")[0] and "330 W†" in sim
    assert "Cross-device" in sim
    for garmin_only in ("Body Battery", "Garmin readiness", "Training effect", "Garmin's baseline"):
        assert garmin_only not in md
    assert "Apple's own estimate" in md or "Power:HR decoupling: not available" in md


def test_sparse_apple_hrv_is_labelled_as_such(tmp_path):
    # (6) Two Apple spot readings in the night: never presented as Garmin's overnight HRV
    _, _, conn, sid = mixed_history(tmp_path)
    d = (ANCHOR + timedelta(days=2)).isoformat()
    conn.daily_observation.update_one({"source": "fixture", "metric": "hrv_overnight_avg", "local_date": d},
                                      {"$set": {"value": 36.0, "state": "measured", "method": "apple_sdnn", "label": "4 readings",
                                                "unit": "ms"}}, upsert=True)
    md = run_export.markdown(conn, "fixture", sid, app_version="test")[1]
    line = next(x for x in md.splitlines() if x.startswith("HRV last night"))
    assert "Apple Watch spot readings" in line and "not an overnight average like Garmin's" in line and "SDNN" in line


def test_missing_running_dynamics_and_power_are_absent_not_zero(tmp_path):
    # (10) An Apple run without power or running dynamics: said so, never shown as 0
    _, _, conn, sid = mixed_history(tmp_path, dynamics=False, power=False)
    md = run_export.markdown(conn, "fixture", sid, app_version="test")[1]
    assert "Power:HR decoupling: not available" in md and "| 0 W" not in md and "Power: **not comparable**" not in md


def test_our_vo2_trend_never_spans_two_watches(monkeypatch):
    # (5) Runner Sidekick's estimate: same method on every watch, but its trend stays within one
    today = date(2026, 11, 15)
    monkeypatch.setattr("sidekick.scores.vo2_maker", lambda conn, d: "Runner Sidekick")
    monkeypatch.setattr("sidekick.scores.vo2_on", lambda conn, s, d, t: (48.0, d) if d == today else (46.4, d - timedelta(days=1)))
    watches = {today: {"garmin", "apple"}, today - timedelta(days=28): {"garmin"}}
    monkeypatch.setattr("sidekick.cardio.own_vo2_watches", lambda conn, s, d: watches[d])
    sig = progress.vo2_signal(None, "fixture", today)
    assert sig["direction"] is None and "different watches" in sig["say"]
    watches[today] = {"garmin"}
    assert progress.vo2_signal(None, "fixture", today)["direction"] == "improving"


def test_ai_input_gets_the_watch_windows_and_comparability(tmp_path):
    # (8) The model is told the device, both pacing windows, the drift measurement's suitability and the cross-watch flags
    from sidekick import run_ai
    _, _, conn, sid = mixed_history(tmp_path)
    rp.build_post_run(conn, "fixture", sid, True)
    b = run_ai.bundle(conn, "fixture", sid, ANCHOR + timedelta(days=2))
    assert b.items["run:this"]["watch"] == "Apple Watch"
    assert "warm-up included" in b.items["run:pacing"]["halves_whole_run"] and b.items["run:pacing"]["drift_window"]
    assert b.items["run:drift"]["suitability"] in ("good", "caution")
    assert b.items["run:comparability"]["from_another_watch"] >= 1 and b.items["run:comparability"]["power_comparable"] is False
    for rule in ("measure different stretches", "Never compare power in watts", 'automatically followed by "easy"'):
        assert rule in run_ai.SYSTEM
