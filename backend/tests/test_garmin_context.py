"""Garmin's numbers with their context: what its readiness was built from, its HRV baseline band, a resting HR from a day
without a night on the watch, in-run Performance Condition and stamina, training status by day, and the current race
prediction (the newer of the snapshot and the daily history). Payload shapes as the real ones from 13 and 25 Oct 2026."""

from datetime import datetime, timezone

from sidekick import reports as rp
from sidekick import run_export
from sidekick.connectors import garmin as g
from sidekick.db import set_setting
from sidekick.numbers import current_predictions
from test_run_export import no_net, synced

READY_25 = {"calendarDate": "2026-10-25", "timestamp": "2026-10-25T11:09:05.0", "level": "HIGH", "score": 94, "recoveryTime": 1,
            "sleepScoreFactorFeedback": "NONE", "recoveryTimeFactorFeedback": "GOOD", "acwrFactorFeedback": "VERY_GOOD",
            "hrvFactorFeedback": "NONE", "stressHistoryFactorFeedback": "NONE", "sleepHistoryFactorFeedback": "NONE", "validSleep": False}
READY_13 = {**READY_25, "timestamp": "2026-10-13T03:29:13.0", "level": "MODERATE", "score": 70, "recoveryTime": 616, "validSleep": True,
            "sleepScoreFactorFeedback": "GOOD", "hrvFactorFeedback": "GOOD"}


def by_metric(obs):
    return {o.metric: o for o in obs}


def test_readiness_says_what_it_was_built_from():
    o = by_metric(g.normalise_readiness("2026-10-25", READY_25))
    assert o["garmin_training_readiness"].value == 94 and o["garmin_training_readiness"].label == "HIGH"  # unchanged
    assert o["garmin_readiness_inputs"].value == 0 and "sleep:NONE" in o["garmin_readiness_inputs"].label
    assert o["garmin_recovery_time_min"].value == 1 and o["garmin_recovery_time_min"].observed_end == "2026-10-25T11:09:05Z"
    assert by_metric(g.normalise_readiness("2026-10-13", READY_13))["garmin_readiness_inputs"].value == 1
    # No readiness that day: nothing invented
    none = by_metric(g.normalise_readiness("2026-10-26", {}))
    assert all(x.state == "not_measured" for x in none.values())


def test_hrv_band_and_overnight_wear():
    o = by_metric(g.normalise_hrv("2026-10-13", {"hrvSummary": {"lastNightAvg": 42, "weeklyAvg": 36, "status": "BALANCED",
                                                                 "baseline": {"balancedLow": 35, "balancedUpper": 47}}}))
    assert (o["hrv_overnight_avg"].value, o["hrv_overnight_avg"].label) == (42, "BALANCED")  # unchanged
    assert (o["hrv_baseline_low"].value, o["hrv_baseline_high"].value) == (35, 47)
    empty = by_metric(g.normalise_hrv("2026-10-25", {}))  # a night on the other watch: not measured, never 0
    assert empty["hrv_baseline_low"].state == "not_measured" and empty["hrv_overnight_avg"].state == "not_measured"
    asleep = by_metric(g.normalise_user_summary("2026-10-25", {"restingHeartRate": 56, "measurableAsleepDuration": 0}))
    assert asleep["asleep_measured_s"].state == "measured" and asleep["asleep_measured_s"].value == 0  # 0 is the reading


def test_performance_condition_keeps_zero_and_leading_gaps():
    start = datetime(2026, 10, 25, 17, 22, tzinfo=timezone.utc)
    keys = ["directTimestamp", "directHeartRate", "directPerformanceCondition", "directAvailableStamina"]
    rows = [[(start.timestamp() + i) * 1000, 150, pc, st] for i, (pc, st) in enumerate([(None, 99), (None, 98), (3, 97), (0, 90), (-1, 51)])]
    s = g.normalise_samples({"metricDescriptors": [{"key": k, "metricsIndex": i} for i, k in enumerate(keys)],
                             "activityDetailMetrics": [{"metrics": r} for r in rows]}, start)
    assert s.dyn["pc"] == [None, None, 3, 0, -1] and s.dyn["stamina"][-1] == 51
    # An older watch without them: no keys, no error
    s2 = g.normalise_samples({"metricDescriptors": [{"key": k, "metricsIndex": i} for i, k in enumerate(keys[:2])],
                              "activityDetailMetrics": [{"metrics": r[:2]} for r in rows]}, start)
    assert not s2.dyn or ("pc" not in s2.dyn and "stamina" not in s2.dyn)


def test_current_prediction_is_the_newest():
    conn, _ = synced()
    set_setting(conn, "garmin_fitness", {"race_predictions": {"date": "2026-10-10", "5k": 1556, "10k": 3346}})
    set_setting(conn, "garmin_predictions", [{"date": "2026-10-24", "5k": 1570}, {"date": "2026-10-25", "5k": 1578, "10k": 3397}])
    assert current_predictions(conn)["5k"] == 1578  # the snapshot from 10 Oct was stale
    set_setting(conn, "garmin_predictions", [{"date": "2026-10-01", "5k": 1600}])
    assert current_predictions(conn)["5k"] == 1556  # the snapshot is newer this time


def test_export_carries_garmin_context_for_a_garmin_run():
    conn, sid = synced()
    a = rp.activity_by_source_id(conn, "fixture", sid)
    day = a["local_date"]
    set_setting(conn, "timezone", "Asia/Jerusalem")
    for m, v, label, end in (("resting_hr", 56, None, None), ("asleep_measured_s", 0, None, None),
                             ("garmin_training_readiness", 94, "HIGH", None),
                             ("garmin_readiness_inputs", 0, "sleep:NONE,recovery:GOOD,load:VERY_GOOD,hrv:NONE", "2026-09-30T11:09:05Z"),
                             ("garmin_recovery_time_min", 600, None, "2026-09-30T11:09:05Z"),
                             ("hrv_overnight_avg", 42, "BALANCED", None), ("hrv_baseline_low", 35, None, None), ("hrv_baseline_high", 47, None, None)):
        conn.daily_observation.replace_one({"source": "fixture", "local_date": day, "metric": m},
                                           {"source": "fixture", "local_date": day, "metric": m, "value": v, "state": "measured",
                                            "label": label, "observed_end": end, "unit": "x"}, upsert=True)
    set_setting(conn, "garmin_status_history", [{"date": day, "phrase": "MAINTAINING_3", "acute_load": 202, "chronic_min": 175,
                                                 "chronic_max": 329, "load_focus": "AEROBIC_LOW_SHORTAGE"}])
    set_setting(conn, "garmin_threshold", {"points": [{"date": "2026-09-01", "hr": 166, "speed_m_s": 3.086}]})
    set_setting(conn, "garmin_predictions", [{"date": day, "5k": 1578, "10k": 3397}])
    md = run_export.markdown(conn, "fixture", sid, fetch=no_net)[1]
    assert "Resting HR: **56 bpm (daytime only: the watch wasn't worn overnight)**" in md
    assert "within Garmin's baseline 35–47 ms" in md
    assert "Training readiness (Garmin): **94 / 100 (high), at 14:09, without sleep or HRV (no night on this watch), recovery time then 10 h**" in md
    sec = md[md.index("## Training load and thresholds (Garmin)"):]
    assert "Training status: **Maintaining**" in sec and "Acute load: **202** (Garmin's range 175–329)" in sec
    assert "Load focus: **aerobic low shortage**" in sec and "Lactate threshold (Garmin, 2026-09-01): **166 bpm · 5:24 /km**" in sec
    assert "Race prediction (Garmin, " in sec and "5K **26:18**" in sec
    assert "Partial history" not in sec  # no other watch's runs here
    assert "Export schema: **Runner Sidekick LLM Export v2.1**" in md


def test_run_rows_from_garmin():
    from sidekick.connectors.base import Samples
    conn, _ = synced()
    set_setting(conn, "garmin_threshold", {"points": [{"date": "2026-10-06", "hr": 166}, {"date": "2026-11-01", "hr": 170}]})
    s = Samples(t=[0, 1, 2, 3], hr=[150] * 4, speed=[3] * 4, dist=[0, 3, 6, 9], elev=[0] * 4, cad=[170] * 4,
                dyn={"pc": [None, 3, -2, -1], "stamina": [99, 80, 60, 51]})
    rows = {x["label"]: x["value"] for x in rp.garmin_extra(conn, {"local_date": "2026-10-25", "avg_hr": 155}, s)}
    assert rows == {"Performance condition (Garmin)": "+3 → -1 (lowest -2)", "Stamina left at the end (Garmin)": "51%",
                    "Average HR vs Garmin's threshold": "93% of 166 bpm"}  # the threshold as of the run's day, not a later one
    assert rp.garmin_extra(conn, {"local_date": "2026-09-01", "avg_hr": 155}, None) == []  # nothing from Garmin: no rows


def test_daytime_resting_hr_is_shown_but_not_compared():
    from datetime import date, timedelta
    conn, _ = synced()
    d = date(2026, 9, 30)
    for i in range(1, 21):  # three weeks of ordinary overnight values
        k = (d - timedelta(days=i)).isoformat()
        conn.daily_observation.replace_one({"source": "fixture", "local_date": k, "metric": "resting_hr"},
                                           {"source": "fixture", "local_date": k, "metric": "resting_hr", "value": 50.0, "unit": "bpm",
                                            "state": "measured", "method": "garmin_daily_rhr", "label": None, "source_record_id": None}, upsert=True)
    for k, v in ((d.isoformat(), 62.0), ((d - timedelta(days=3)).isoformat(), 70.0)):  # two days without a night on the watch
        conn.daily_observation.replace_one({"source": "fixture", "local_date": k, "metric": "resting_hr"},
                                           {"source": "fixture", "local_date": k, "metric": "resting_hr", "value": v, "unit": "bpm",
                                            "state": "measured", "method": "garmin_daily_rhr", "label": None, "source_record_id": None}, upsert=True)
        conn.daily_observation.replace_one({"source": "fixture", "local_date": k, "metric": "asleep_measured_s"},
                                           {"source": "fixture", "local_date": k, "metric": "asleep_measured_s", "value": 0, "unit": "s",
                                            "state": "measured"}, upsert=True)
    row = conn.daily_observation.find_one({"source": "fixture", "local_date": d.isoformat(), "metric": "resting_hr"})
    f = rp.metric_finding(conn, "fixture", "resting_hr", d, row)
    assert f["status"] == "not_compared" and f["observed"]["value"] == 62 and f["comparison"] is None  # shown, not compared
    assert (d - timedelta(days=3)).isoformat() not in rp.rhr_series(conn, "fixture", d.isoformat())  # nor part of the usual
    # An ordinary day the next day is compared against the usual without the daytime values
    k = (d + timedelta(days=1)).isoformat()
    conn.daily_observation.replace_one({"source": "fixture", "local_date": k, "metric": "resting_hr"},
                                       {"source": "fixture", "local_date": k, "metric": "resting_hr", "value": 51.0, "unit": "bpm",
                                        "state": "measured", "method": "garmin_daily_rhr", "label": None, "source_record_id": None}, upsert=True)
    f2 = rp.metric_finding(conn, "fixture", "resting_hr", d + timedelta(days=1),
                           conn.daily_observation.find_one({"source": "fixture", "local_date": k, "metric": "resting_hr"}))
    assert f2["status"] != "not_compared" and f2["comparison"]["median"] == 50
