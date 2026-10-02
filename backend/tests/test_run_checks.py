from sidekick import run_checks as rc


def split(i, pace, cad=170, climb=5, gap=None):
    return {"idx": i, "pace_s_per_km": pace, "complete": True, "cadence_spm": cad, "elevation_gain_m": climb, "gap_pace_s_per_km": gap or pace}


def report(splits, kind=None, te=None, climb=20):
    return {"splits": splits, "intent": {"kind": kind} if kind else None, "activity": {"source_id": "x", "elevation_gain_m": climb},
            "decoupling": {"eligible": False}, "garmin_metrics": {"aerobicTrainingEffect": te} if te is not None else {}}


def by_id(checks):
    return {c["id"]: c for c in checks}


def test_pacing_cadence_and_training_effect_verdicts(monkeypatch):
    monkeypatch.setattr(rc.rp, "hr_zones", lambda conn: None)  # no zones: the effort check is skipped
    c = by_id(rc.build(None, "x", report([split(i, p) for i, p in enumerate([340, 342, 344, 352, 354, 356])], "easy", 4.6)))
    assert c["pacing"]["verdict"] == "ok" and "Slowed 12 s/km" in c["pacing"]["say"]
    assert c["cadence"]["verdict"] == "good" and "Steady at 170" in c["cadence"]["say"]
    assert c["training_effect"]["verdict"] == "low" and "a lot for an easy run" in c["training_effect"]["say"]
    even = by_id(rc.build(None, "x", report([split(i, 350, cad=150 + 5 * i) for i in range(6)], te=2.5)))
    assert even["pacing"]["say"] == "Even all the way" and even["cadence"]["say"].startswith("Varied")
    assert even["training_effect"]["verdict"] == "info" and "maintaining" in even["training_effect"]["say"]
    assert "hills" not in even  # under 30 m of climbing isn't worth a line
