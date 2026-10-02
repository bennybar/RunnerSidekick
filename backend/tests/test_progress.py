from datetime import date

from sidekick import progress


def fake(monkeypatch, vo2, eff, drift):
    monkeypatch.setattr(progress, "vo2_signal", lambda c, s, t: progress.signal("vo2", "Aerobic estimate", vo2, "x", "n"))
    monkeypatch.setattr(progress, "efficiency_signal", lambda c, s, t: progress.signal("efficiency", "Efficiency", eff, "x", "n"))
    monkeypatch.setattr(progress, "drift_signal", lambda c, s, t: progress.signal("drift", "Durability", drift, "x", "n"))
    return progress.build(None, "x", date(2026, 10, 2))


def test_verdict_needs_two_signals_and_confidence_counts_agreement(monkeypatch):
    assert fake(monkeypatch, "improving", None, None)["verdict"] == "insufficient"
    p = fake(monkeypatch, "declining", "improving", "improving")
    assert p["verdict"] == "improving" and p["confidence"] == "medium" and p["summary"].startswith("Getting fitter")
    assert "aerobic estimate slipped" in p["summary"]
    p = fake(monkeypatch, "stable", "stable", "stable")
    assert p["verdict"] == "stable" and p["confidence"] == "high"
    assert fake(monkeypatch, "declining", "declining", None)["verdict"] == "declining"
