"""Regression tests for the 2026-11-03 calculation audit."""
from sidekick import readiness as rd
from sidekick import weather as wx
from sidekick.analytics import running as rn

from test_race import ANCHOR, synced


def test_a_run_labelled_hot_is_treated_as_hot():
    # Middle hour under the bar, the finish over it: the label and the flag agree (the hottest of start, middle, finish)
    w = {"temperature_2m": 24.0, "dew_point_2m": 17.0, "apparent_temperature": 25.0, "end": {"dew_point_2m": 18.5, "apparent_temperature": 28.0}}
    h = wx.heat(w)
    assert h["stress"] == "Hot" and h["hot"] is True
    cool = wx.heat({"temperature_2m": 15.0, "dew_point_2m": 8.0, "apparent_temperature": 14.0})
    assert cool["stress"] == "Comfortable" and cool["hot"] is False


def test_sleep_never_reads_60_minutes():
    m = {"findings": [{"metric": "sleep_duration", "observed": {"value": 25199.0}, "comparison": {"median": 25000.0},
                       "sparkline": [], "status": "within"}], "recommendation": {"rule_id": "R1"}}
    sleep = next(p for p in rd.build(synced(), "fixture", ANCHOR, m)["components"] if p["id"] == "sleep")
    assert sleep["value"] == "7 h 00 min"


def test_fade_names_a_split_in_the_second_half_not_the_middle_one():
    # 5 splits: halves are #1–2 and #4–5; the middle one is slow but in neither half
    pace = [300, 300, 306, 304, 312]
    splits = [rn.Split(k, 1000.0, p, p, 150.0, 0.0, float(p), True) for k, p in enumerate(pace)]
    story = rn.run_story(splits, [{}] * 5, lambda p: f"{int(p)}")
    assert any("faded" in x and "from km #5" in x for x in story)


def test_held_maximum_skips_a_stretch_flagged_as_cadence_lock():
    from sidekick import cardio
    from sidekick.connectors.base import Samples
    # 30 minutes steady at 150 bpm and 3 m/s, with 90 s locked onto the cadence (172) mid-run
    t = [float(x) for x in range(1800)]
    hr = [172.0 if 900 <= x < 990 else 150.0 for x in range(1800)]
    s = Samples(t, hr, [3.0] * 1800, [3.0 * x for x in t], [10.0] * 1800, [172.0] * 1800)
    from sidekick.analytics import running as rn
    assert rn.hr_quality(s)["stretches"]  # the check flags it
    assert cardio.sustained_max(s) < 152   # so the maximum stays the real 150, not 172


def test_laps_are_placed_by_their_own_start_times():
    from sidekick.connectors.base import Samples
    # Two 600 s laps with a 60 s gap between them (a recording app's laps): the second lap's samples start at 660 s
    t = [float(x) for x in range(1260)]
    speed = [2.5 if x < 660 else 4.0 for x in range(1260)]
    s = Samples(t, [150.0] * 1260, speed, [sum(speed[:k]) for k in range(1260)], [10.0] * 1260, [170.0] * 1260)
    laps = [{"idx": 0, "elapsed_s": 600.0, "distance_m": 1500.0, "start_utc": "2026-11-01T06:00:00Z"},
            {"idx": 1, "elapsed_s": 600.0, "distance_m": 2400.0, "start_utc": "2026-11-01T06:11:00Z"}]
    d = rn.split_details(s, laps, None)
    assert d[1]["gap_pace_s_per_km"] == 250.0  # all 4 m/s: none of the first lap's slower samples
