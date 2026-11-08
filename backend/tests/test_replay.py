"""Made-up runners' histories played through the app one morning at a time (sidekick/replay.py): every scenario's
coach-sense checks and the cross-screen consistency checks pass, and the checks actually meet the cases they're about."""

from sidekick import replay


def test_every_replayed_history_gets_sensible_consistent_advice():
    results = replay.run()
    failed = {n: r["failures"] for n, r in results.items() if r["failures"]}
    assert not failed, "\n".join(f"{n}: {f}" for n, fs in failed.items() for f in fs)

    def ran(name, pred):
        return sum(1 for s in results[name]["snaps"] if pred(s))
    yrun = lambda s: s["yesterday"].run  # noqa: E731
    # The checks met their cases (a check with nothing to look at would pass vacuously)
    assert ran("illness", lambda s: s["spec"].ill) >= 5 and ran("illness", lambda s: "ease back in" in str(s["readiness"]["hold_reason"])) >= 2
    assert ran("missing_nights", lambda s: not s["spec"].worn) >= 3
    assert ran("hot_summer", lambda s: yrun(s) and yrun(s).hot and s["run_checks"]) >= 6
    assert ran("hilly", lambda s: yrun(s) and yrun(s).hilly and s["run_checks"] and s["run_checks"]["pacing"][0] == "info") >= 3
    assert ran("hr_dropout", lambda s: yrun(s) and yrun(s).dropout and s["run_checks"]) >= 3
    assert ran("hr_dropout", lambda s: yrun(s) and not yrun(s).dropout and s["run_checks"] and "effort" in s["run_checks"]) >= 6
    assert ran("race_build", lambda s: s["week"] and s["week"]["phase"] == "taper") >= 5
    assert ran("race_build", lambda s: s["race"] and s["race"]["days_to_go"] == 0 and s["next_run"]["kind"] == "race") == 1
    assert ran("routine", lambda s: yrun(s) and yrun(s).kind == "long") >= 3
