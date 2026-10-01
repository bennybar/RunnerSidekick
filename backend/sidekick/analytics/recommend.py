"""Conservative, explainable training-guidance rules. Documented in docs/analysis-rules.md.

Signals are grouped so correlated inputs count once:
  overnight_autonomic : resting HR high OR HRV low (both overnight autonomic measures)
  sleep               : main sleep short
  subjective          : check-in energy/recovery <= 2, or soreness >= 4
  load                : trailing-7-day moving time > 1.5x the prior 4-week weekly mean
  sustained           : an autonomic or sleep change beyond threshold for 3 consecutive days
Garmin composite scores (readiness, Body Battery, sleep score) are displayed but never used
here, because they already incorporate sleep/HRV and would double count.
"""

from __future__ import annotations

RULES_VERSION = "rules-1.4"  # 1.2: no reassurance without data (R1c/R1d); 1.3: R1e; 1.4: app-initiated check-ins

STATES = ("usual_plan", "consider_easier", "insufficient_data")


def recommend(signals: dict[str, list[str]], checkin: dict | None, has_overnight_data: bool,
              any_baseline: bool) -> dict:
    """signals: group -> finding IDs supporting it (only groups that fired)."""
    evidence = sorted({fid for ids in signals.values() for fid in ids})
    if checkin and (checkin.get("pain") or checkin.get("illness")):
        what = " and ".join(w for w, f in (("pain", checkin.get("pain")), ("illness", checkin.get("illness"))) if f)
        return _r("consider_easier", "R0", f"You reported {what} today. That takes priority over any watch reading.",
                  ["checkin"] + evidence, suppress=True,
                  uncertainty="Based on your own report. If symptoms persist or are severe, seek professional advice.")
    groups = sorted(signals)
    if groups == ["subjective"]:
        return _r("consider_easier", "R4s",
                  "You reported feeling less recovered" + (", while your overnight readings are within your usual ranges."
                                                           if has_overnight_data and any_baseline else "."),
                  evidence, suppress=True,
                  uncertainty="How you feel counts. An easier session is a reasonable choice today.")
    # Without overnight data or personal ranges, nothing supports "your readings look typical", even with a good check-in.
    if not has_overnight_data:
        if checkin:
            return _r("insufficient_data", "R1c", "No overnight readings yet. Your check-in looks fine, so this is based on how you feel.",
                      ["checkin"], suppress=True, uncertainty="Watch data may still be syncing.")
        return _r("insufficient_data", "R1", "No overnight data or check-in for today yet.", [], suppress=True,
                  uncertainty="Watch data may still be syncing.")
    if not any_baseline and groups:
        # Something stands out, but there are no personal ranges to say the rest is typical: stay cautious
        what = "Your recent running is well above your usual" if "load" in groups else f"One signal stands out ({_label(groups[0])})"
        return _r("usual_plan", "R1e",
                  f"{what}, and your personal ranges are still being learned.", evidence + (["checkin"] if checkin else []),
                  suppress=True, uncertainty="Without personal ranges, overnight readings can't be called typical yet.")
    if not any_baseline and not groups:
        if checkin:
            return _r("insufficient_data", "R1d", "Still learning your personal ranges. Your check-in looks fine.", ["checkin"],
                      suppress=True, uncertainty="Comparisons need 14 days with data in the last 28.")
        return _r("insufficient_data", "R1b", "Still learning your personal ranges (needs 14 days with data in the last 28).", [],
                  suppress=True, uncertainty="Comparisons need more history.")
    if len(groups) >= 2:
        return _r("consider_easier", "R2", f"Several separate signals point the same way ({', '.join(_label(g) for g in groups)}).",
                  evidence + (["checkin"] if checkin else []), suppress=True,
                  uncertainty="These readings are associations, not a diagnosis; how you feel matters most.")
    if len(groups) == 1 and not checkin:
        return _r("usual_plan", "R3", f"One signal is outside your usual range ({_label(groups[0])}). Keep the effort comfortable.",
                  evidence, suppress=True, uncertainty="A single reading often reflects day-to-day noise.")
    if len(groups) == 1:
        return _r("usual_plan", "R4", f"One signal is outside your usual range ({_label(groups[0])}), but nothing else points the same way.",
                  evidence + ["checkin"], suppress=False,
                  uncertainty="Worth keeping an eye on rather than changing plans.")
    return _r("usual_plan", "R5", "Your readings are within your usual ranges.", evidence + (["checkin"] if checkin else []),
              suppress=not has_overnight_data, uncertainty=None if has_overnight_data else "Some overnight data is missing.")


def _label(group: str) -> str:
    return {"overnight_autonomic": "overnight heart rate/HRV", "sleep": "sleep", "subjective": "how you feel",
            "load": "recent training load", "sustained": "a change lasting several days"}[group]


def _r(state: str, rule: str, reason: str, evidence: list[str], suppress: bool, uncertainty: str | None) -> dict:
    return {"state": state, "rule_id": rule, "reason": reason, "evidence_ids": evidence,
            "suppress_intensity": suppress, "uncertainty": uncertainty, "rules_version": RULES_VERSION}
