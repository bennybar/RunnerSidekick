from datetime import date, datetime, timedelta

from sidekick.analytics import insights as ins
from sidekick.analytics.running import Split
from sidekick.connectors.base import Samples

ZONES = {"floors": [95, 113, 132, 151, 170], "method": "HR_MAX", "max_hr": 189}


def run(i, hr=160.0, speed=3.0, device="w1", start_hour=7, day0=date(2026, 7, 1), splits=None, load=None, minutes=40):
    d = day0 + timedelta(days=2 * i)
    t = [float(x) for x in range(0, minutes * 60 + 1, 5)]
    s = Samples(t, [hr] * len(t), [speed] * len(t), [speed * x for x in t], [0.0] * len(t), [170.0] * len(t))
    sp = splits or [Split(k, 1000.0, 1000 / speed, 1000 / speed, hr, 0.0, 1000 / speed, True) for k in range(6)]
    return ins.RunData(f"r{i}", d.isoformat(), datetime.combine(d, datetime.min.time()).replace(hour=start_hour), device, 7000.0,
                       minutes * 60.0, load, s, sp, "steady")


def test_intensity_pattern_when_mostly_hard():
    i = ins.intensity_distribution([run(k, hr=160) for k in range(10)], ZONES)
    assert i["verdict"] == "pattern" and i["effect"]["hard_share"] > 0.9 and i["sample_size"] == 10


def test_intensity_needs_zones_and_enough_runs():
    assert ins.intensity_distribution([run(k) for k in range(10)], None)["verdict"] == "not_enough_data"
    assert ins.intensity_distribution([run(k) for k in range(3)], ZONES)["verdict"] == "not_enough_data"


def test_efficiency_improving_within_one_device():
    runs = [run(k, hr=155, speed=2.8 + 0.02 * k) for k in range(12)]  # same HR, faster over ~3 weeks
    i = ins.efficiency_trend(runs)
    assert i["verdict"] == "pattern" and "Faster" in i["headline"]


def test_watch_change_does_not_create_a_trend():
    # Flat within each watch; the second watch reads pace differently. Pooling would show a fake improvement.
    runs = [run(k, hr=155, speed=2.8, device="old") for k in range(12)] + [run(k + 12, hr=155, speed=3.1, device="new") for k in range(12)]
    i = ins.efficiency_trend(runs)
    assert i["verdict"] == "no_clear_pattern"
    assert {e["device"] for e in i["effect"]["eras"]} == {"old", "new"}


def test_pacing_fade_detected():
    fade = [Split(k, 1000.0, 300.0 + 6 * k, 300.0 + 6 * k, 160.0, 0.0, 300.0 + 6 * k, True) for k in range(6)]
    i = ins.pacing_pattern([run(k, splits=fade) for k in range(10)])
    assert i["verdict"] == "pattern" and i["effect"]["positive"] == 10


def test_evening_sleep_reports_null_result_with_counts():
    runs = [run(k, start_hour=20) for k in range(10)]
    nights = {(r.local_start.date() + timedelta(days=1)).isoformat() for r in runs}
    days = [(date(2026, 7, 1) + timedelta(days=k)).isoformat() for k in range(25)]
    obs = {"sleep_duration": {d: 25200.0 for d in days}, "hrv_overnight_avg": {d: 40.0 for d in days}}
    i = ins.evening_runs_sleep(runs, obs, {})
    assert i["verdict"] == "no_clear_pattern" and i["effect"]["nights_after"] == len([d for d in days if d in nights])


def test_evening_sleep_detects_shorter_sleep():
    runs = [run(k, start_hour=20) for k in range(10)]
    nights = {(r.local_start.date() + timedelta(days=1)).isoformat() for r in runs}
    days = [(date(2026, 7, 1) + timedelta(days=k)).isoformat() for k in range(25)]
    obs = {"sleep_duration": {d: (23400.0 if d in nights else 25800.0) for d in days}}
    i = ins.evening_runs_sleep(runs, obs, {})
    assert i["verdict"] == "pattern" and i["effect"]["sleep_diff_s"] == -2400


def test_theil_sen_is_robust_to_one_outlier():
    pts = [(x, 2.0 * x) for x in range(10)] + [(10, 500.0)]
    assert abs(ins.theil_sen(pts) - 2.0) < 0.5
