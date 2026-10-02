"""One plain sentence per reading on Today: how good the value is (against your usual range and, where a reference
exists, people of your age and sex) and what the reading means. Deterministic wording from the numbers."""

from __future__ import annotations

MEANING = {
    "sleep_duration": "Most adults need 7–9 hours; enough sleep supports recovery and how training feels.",
    "resting_hr": "Your heart rate at rest; lower usually goes with better aerobic fitness, and a rise above your usual can mean "
                  "fatigue, stress, heat or illness.",
    "hrv_overnight_avg": "Variation between heartbeats overnight; higher than your usual tends to mean well recovered, lower "
                         "can mean strain. Compare it only with your own normal.",
    "running_moving_time_7d": "How much you ran in the last 7 days; sudden jumps raise the load on your body.",
    "vo2max": "Garmin's estimate of how much oxygen you can use; it's the best single number for aerobic fitness.",
}


def _usual(f: dict) -> str | None:
    """Against your own usual range, as a clause ("within your usual range"); None while it's being learned."""
    s = f.get("status")
    if s == "within":
        return "within your usual range"
    if s in ("outside", "sustained"):
        d = (f.get("delta") or {}).get("abs") or 0
        return ("above" if d > 0 else "below") + " your usual range" + (" for 3 days" if s == "sustained" else "")
    return None


LEARNING = " Your own usual range is still being learned."


def notes(findings: list[dict], comparison: dict | None) -> dict[str, dict]:
    items = {i["id"]: i for i in (comparison or {}).get("items", []) if i.get("status") == "ok"}
    out: dict[str, dict] = {}
    for f in findings:
        m = f.get("metric")
        if m not in MEANING:
            continue
        v = (f.get("observed") or {}).get("value")
        usual = _usual(f)
        tail = LEARNING if f.get("status") == "learning" else ""
        if v is None:
            last = f.get("last")
            verdict = "Not in yet today." + (f" Your last value was from {last['date']}." if last else "")
        elif m == "sleep_duration":
            h = v / 3600
            band = "within the 7–9 hours most adults need" if 7 <= h <= 9 else ("short of the 7 hours most adults need" if h < 7
                                                                                else "longer than the usual 7–9 hours")
            verdict = f"{int(h)} h {round((h % 1) * 60):02d} min is {band}" + (f" and {usual}." if usual else ".") + tail
        elif m == "resting_hr":
            r = items.get("resting_hr")
            parts = [x for x in (f"lower than about {r['lower_than_pct']}% of {r['group']}" if r else None, usual) if x]
            verdict = (f"{round(v)} bpm is " + " and ".join(parts) + "." if parts else f"{round(v)} bpm.") + tail
            if r and r["lower_than_pct"] >= 75:
                verdict = "Very good: " + verdict
        elif m == "hrv_overnight_avg":
            verdict = (f"Normal for you: {round(v)} ms is {usual}." if f.get("status") == "within" else
                       f"{round(v)} ms is {usual}." if usual else f"{round(v)} ms." + tail)
        else:  # running_moving_time_7d
            mins = round(v / 60)
            verdict = (f"{mins // 60} h {mins % 60:02d} min, well above your recent weeks: a big jump in load." if f.get("status") == "outside"
                       else f"{mins // 60} h {mins % 60:02d} min, similar to your recent weeks.")
        out[m] = {"verdict": verdict, "meaning": MEANING[m]}
    v = items.get("vo2max")
    if v:
        out["vo2max"] = {"verdict": f"{v['value']:.1f} is {v['rating'].lower()} for {v['group']}"
                                    + (f": higher than about {v['percentile']}% of them." if v.get("percentile") is not None else "."),
                         "meaning": MEANING["vo2max"]}
    return out
