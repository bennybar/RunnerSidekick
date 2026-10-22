"""The first real Watchletic run (22 Oct 2026, Galaxy Watch with a COOSPO HW9 armband), checked against its original
FIT samples. tests/data/watchletic_2026-10-22.fit is that file re-encoded without positions (the repo is public):
times, heart rate, cadence, distance, speed, altitude, the lap and the session are as Watchletic wrote them."""

from pathlib import Path

from sidekick import fit, run_export, samsung
from sidekick import reports as rp
from sidekick.analytics import running as rn
from sidekick.db import connect, set_setting, user_db_name

FILE = Path(__file__).parent / "data" / "watchletic_2026-10-22.fit"


def test_cadence_is_steps_and_held_repeats_are_left_out():
    act, summary = fit.parse(FILE.read_bytes())
    s = act.samples
    assert summary["recorder"] == "Watchletic" and summary["laps"] == 1
    # The session says 91 (+0.02) strides a minute; FIT keeps strides, so 182 steps (not doubled twice, not halved)
    assert act.avg_cadence_spm == 182.0
    # Watchletic repeats its last reading in every record (a minute or more at times): past 5 s it's left out, so no
    # value stands for longer than that; what's left is about what the watch's own cadence channel holds (727 records
    # within 5 s of a reading)
    readings = [i for i, c in enumerate(s.cad) if c]
    assert 700 <= len(readings) <= 740
    longest, since = 0.0, 0
    for i in range(1, len(s.t)):
        if not s.cad[i] or s.cad[i] != s.cad[i - 1]:
            since = i
        longest = max(longest, s.t[i] - s.t[since]) if s.cad[i] else longest
    assert longest <= fit.CAD_HOLD_S
    assert 175 <= sorted(c for c in s.cad if c)[len(readings) // 2] <= 195  # steps a minute (strides would be ~92)
    # Heart rate is kept exactly as recorded: nothing filled in or smoothed
    hr = [h for h in s.hr if h is not None]
    assert len(hr) == 1669 and min(hr) == 89 and max(hr) == 181


def test_kilometre_splits_come_from_the_samples_when_the_file_has_one_lap():
    act, _ = fit.parse(FILE.read_bytes())
    assert [round(l.distance_m) for l in act.laps] == [998, 1000, 999, 1002, 998, 35]
    assert sum(l.elapsed_s for l in act.laps) <= act.elapsed_s
    splits = rn.splits_from_laps([{"idx": l.idx, "distance_m": l.distance_m, "moving_s": l.moving_s, "elapsed_s": l.elapsed_s}
                                  for l in act.laps])
    assert [x.complete for x in splits] == [True] * 5 + [False]
    assert [round(x.pace_s_per_km) for x in splits[:5]] == [339, 338, 332, 331, 316]


def test_the_heart_rate_dip_is_flagged_and_left_as_recorded():
    act, _ = fit.parse(FILE.read_bytes())
    q = rn.hr_quality(act.samples)
    assert q["grade"] == "questionable" and len(q["stretches"]) == 1
    x = q["stretches"][0]
    assert 1015 <= x["start_s"] <= 1025 and 1065 <= x["end_s"] <= 1080 and "below" in x["reason"]
    # No gap in the heart-rate record around it: a low reading, not a dropout
    t = [t for t, h in zip(act.samples.t, act.samples.hr) if h is not None and 900 <= t <= 1140]
    assert max(b - a for a, b in zip(t, t[1:])) <= 1.5


def test_watchletic_run_export_names_its_sources_and_splits():
    conn = connect(user_db_name(1, "garmin"))
    set_setting(conn, "watch_history", [{"watch": "samsung", "from": "2026-01-01"}])
    _, runs = fit.ingest(conn, "garmin", FILE.read_bytes())
    sid = runs[0]
    conn.activity.update_one({"source_id": sid}, {"$set": {"recorded_with": "Watchletic",
                                                           "hr_sensor": {"name": "HW9 17586", "kind": "external"}}})
    rp.build_post_run(conn, "garmin", sid, False)
    md = run_export.markdown(conn, "garmin", sid, fetch=lambda *a, **k: None)[1]
    splits = md[md.index("## Pace and splits"):md.index("## Aerobic decoupling")]
    assert [f"\n| {k} |" in splits for k in range(1, 6)] == [True] * 5 and "\n| 6* |" in splits  # 5 km and what's left
    dyn = md[md.index("## Running dynamics"):md.index("## Recovery context") if "## Recovery context" in md else None]
    assert "from Garmin" not in dyn and "Averages and maxima from Watchletic" in dyn and "warm-up included" in dyn
    assert "repeats past 5 s are left out" in dyn
    assert "| Cadence | 182 spm | – | – | – |" in dyn  # too few readings in either half to compare them
    assert "HR source: **External heart-rate sensor HW9 17586 (paired in Watchletic)**" in md
    assert "elevation from the GPS fixes' altitude" in md and "Garmin (device estimate)" not in md
    assert "Sensitivity check, not a correction" in md
