from datetime import date, timedelta

import pytest

from sidekick.analytics import baseline as bl
from sidekick.analytics import running as rn
from sidekick.analytics.recommend import recommend
from sidekick.connectors.base import Samples


def days_before(target: date, values: list[float]) -> dict[str, float]:
    return {(target - timedelta(days=i + 1)).isoformat(): v for i, v in enumerate(values)}


# ---------------------------------------------------------------- baselines

def test_quantile_matches_hand_calculation():
    vals = [1.0, 2.0, 3.0, 4.0]
    assert bl.quantile(vals, 0.25) == pytest.approx(1.75)
    assert bl.quantile(vals, 0.5) == pytest.approx(2.5)
    assert bl.quantile(vals, 0.75) == pytest.approx(3.25)


def test_baseline_excludes_target_day_and_days_outside_window():
    t = date(2026, 9, 30)
    s = days_before(t, [50.0] * 28)
    s[t.isoformat()] = 999.0                                       # target day must not leak in
    s[(t - timedelta(days=29)).isoformat()] = 999.0                # outside the 28-day window
    b = bl.compute_baseline(s, t)
    assert b.n == 28 and b.median == 50.0
    assert b.window_start == "2026-09-02" and b.window_end == "2026-09-29"


def test_baseline_never_spans_device_change():
    t = date(2026, 9, 30)
    s = days_before(t, [50.0] * 28)
    b = bl.compute_baseline(s, t, era_start=date(2026, 9, 20))
    assert b.window_start == "2026-09-20" and b.n == 10 and not b.sufficient


def test_baseline_requires_14_valid_days():
    t = date(2026, 9, 30)
    assert not bl.compute_baseline(days_before(t, [50.0] * 13), t).sufficient
    assert bl.compute_baseline(days_before(t, [50.0] * 14), t).sufficient


def test_missing_days_are_not_zero():
    t = date(2026, 9, 30)
    s = days_before(t, [50.0] * 20)          # only 20 measured days; gaps simply absent
    b = bl.compute_baseline(s, t)
    assert b.n == 20 and b.median == 50.0


def test_deviation_absolute_and_percentage_thresholds():
    t = date(2026, 9, 30)
    b = bl.compute_baseline(days_before(t, [52.0] * 20), t)
    assert bl.deviation("resting_hr", 57.0, b).beyond_threshold          # +5 bpm
    assert not bl.deviation("resting_hr", 56.0, b).beyond_threshold
    assert not bl.deviation("resting_hr", 40.0, b).beyond_threshold      # low RHR is not the concern direction
    hb = bl.compute_baseline(days_before(t, [60.0] * 20), t)
    d = bl.deviation("hrv_overnight_avg", 51.0, hb)                     # -15%
    assert d.delta_pct == pytest.approx(-15.0) and d.beyond_threshold


def test_zero_median_gives_no_percentage():
    t = date(2026, 9, 30)
    b = bl.compute_baseline(days_before(t, [0.0] * 20), t)
    assert bl.deviation("resting_hr", 3.0, b).delta_pct is None


def test_sustained_needs_three_consecutive_days():
    t = date(2026, 9, 30)
    s = days_before(t - timedelta(days=2), [52.0] * 28)
    s[(t - timedelta(days=2)).isoformat()] = 60.0
    s[(t - timedelta(days=1)).isoformat()] = 60.0
    s[t.isoformat()] = 60.0
    assert bl.sustained("resting_hr", s, t)
    s[(t - timedelta(days=1)).isoformat()] = 53.0
    assert not bl.sustained("resting_hr", s, t)


# ---------------------------------------------------------------- running

def steady_samples(hr_first: float, hr_second: float, speed: float = 3.0, total: int = 4200) -> Samples:
    t = [float(x) for x in range(0, total + 1, 5)]
    hr = [hr_first if x < 2400 else hr_second for x in t]
    return Samples(t=t, hr=hr, speed=[speed] * len(t), dist=[speed * x for x in t], elev=[10.0] * len(t), cad=[170.0] * len(t))


def test_decoupling_hand_calculated():
    # Warm-up 0..600 s excluded; segment 600..4200 s; halves split at 2400 s.
    # EF1 = 3/150, EF2 = 3/156 -> 100*(EF1-EF2)/EF1 = 100*(1-150/156) = 3.846%
    r = rn.decoupling(steady_samples(150.0, 156.0), [], 12600.0, 10.0)
    assert r["eligible"]
    assert r["decoupling_pct"] == pytest.approx(3.85, abs=0.01)
    assert r["segment_moving_s"] == 3600


def test_decoupling_ignores_paused_samples_and_long_gaps():
    s = steady_samples(150.0, 150.0)
    # a 2-minute stop with elevated HR, and a 60 s recording gap: neither may carry weight
    for i, t in enumerate(s.t):
        if 3000 <= t < 3120:
            s.speed[i] = 0.0
            s.hr[i] = 175.0
    gap_i = s.t.index(3500.0)
    del s.t[gap_i:gap_i + 12], s.hr[gap_i:gap_i + 12], s.speed[gap_i:gap_i + 12]
    del s.dist[gap_i:gap_i + 12], s.elev[gap_i:gap_i + 12], s.cad[gap_i:gap_i + 12]
    r = rn.decoupling(s, [], 12600.0, 10.0)
    assert r["eligible"] and r["decoupling_pct"] == pytest.approx(0.0, abs=1e-6)


def test_uniform_interval_lap_labels_do_not_imply_intervals():
    laps = [{"idx": i, "intensity": "INTERVAL"} for i in range(8)]
    assert rn.classify(steady_samples(150.0, 150.0), laps)["kind"] == "steady"
    assert rn.classify(steady_samples(150.0, 150.0), laps + [{"idx": 8, "intensity": "REST"}])["kind"] == "variable"


def test_interval_session_not_eligible():
    t = [float(x) for x in range(0, 3601, 5)]
    speed = [4.2 if (x // 180) % 2 == 0 else 2.2 for x in t]
    s = Samples(t, [150.0] * len(t), speed, [0.0] * len(t), [0.0] * len(t), [170.0] * len(t))
    r = rn.decoupling(s, [], 10000.0, 0.0)
    assert not r["eligible"] and r["classification"]["kind"] == "variable"


def test_hr_dropout_makes_run_ineligible():
    s = steady_samples(150.0, 150.0)
    for i, t in enumerate(s.t):
        if 1000 <= t < 1500:
            s.hr[i] = None
    r = rn.decoupling(s, [], 12600.0, 10.0)
    assert not r["eligible"] and any("coverage" in x for x in r["reasons"])


def test_hilly_run_not_eligible():
    r = rn.decoupling(steady_samples(150.0, 150.0), [], 10000.0, 200.0)  # 20 m/km
    assert not r["eligible"] and any("hilly" in x for x in r["reasons"])


def test_incomplete_final_split_is_flagged_and_pace_uses_moving_time():
    laps = [{"idx": i, "distance_m": 1000.0, "moving_s": 300.0, "elapsed_s": 310.0} for i in range(5)]
    laps.append({"idx": 5, "distance_m": 420.0, "moving_s": 130.0, "elapsed_s": 130.0})
    sp = rn.splits_from_laps(laps)
    assert [s.complete for s in sp] == [True] * 5 + [False]
    assert sp[0].pace_s_per_km == pytest.approx(300.0)


def test_similar_runs_matching_is_transparent():
    target = {"source_id": "t", "sport": "running", "distance_m": 10000.0, "moving_s": 3000.0, "avg_hr": 150.0,
              "elevation_gain_m": 50.0, "start_utc": "2026-09-30T05:00:00Z", "local_date": "2026-09-30"}
    def cand(i, dist, gain=50.0, cls="steady", pace=310.0):
        return {"source_id": f"c{i}", "sport": "running", "distance_m": dist, "moving_s": pace * dist / 1000, "avg_hr": 152.0,
                "elevation_gain_m": gain, "start_utc": f"2026-09-{10 + i:02d}T05:00:00Z", "local_date": f"2026-09-{10 + i:02d}",
                "classification": cls}
    cands = [cand(1, 9500), cand(2, 10500), cand(3, 11000), cand(4, 13000), cand(5, 10000, gain=200), cand(6, 10000, cls="variable")]
    r = rn.similar_runs(target, cands)
    assert {x["source_id"] for x in r["runs"]} == {"c1", "c2", "c3"}
    assert r["summary"]["pace_delta_s_per_km"] == pytest.approx(-10.0)


# ---------------------------------------------------------------- rules

def test_pain_overrides_everything():
    r = recommend({}, {"pain": True, "illness": False}, True, True)
    assert r["state"] == "consider_easier" and r["suppress_intensity"]


def test_single_low_hrv_does_not_cancel_run_after_checkin():
    r = recommend({"overnight_autonomic": ["m:hrv"]}, {"energy": 4, "pain": False, "illness": False}, True, True)
    assert r["state"] == "usual_plan"


def test_feeling_flat_with_typical_readings_suppresses_intensity():
    r = recommend({"subjective": ["checkin"]}, {"energy": 2, "pain": False, "illness": False}, True, True)
    assert r["rule_id"] == "R4s" and r["state"] == "consider_easier" and r["suppress_intensity"]


def test_single_signal_without_checkin_asks_for_checkin():
    assert recommend({"sleep": ["m:sleep"]}, None, True, True)["state"] == "check_in_needed"


def test_two_independent_signals_suggest_easier():
    assert recommend({"sleep": ["a"], "overnight_autonomic": ["b"]}, None, True, True)["state"] == "consider_easier"


def test_no_data_is_insufficient():
    assert recommend({}, None, False, False)["state"] == "insufficient_data"
