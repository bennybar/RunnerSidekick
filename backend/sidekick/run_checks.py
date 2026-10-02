"""How a run went, as a few plain checks, each with a verdict (good / ok / low) or "info" where there's nothing to
judge: pacing, effort against what the run was meant to be, cadence, heart-rate drift, hills and Garmin's training
effect. Calculated from the run's report when the run is opened; no language model, and stored reports don't change."""

from __future__ import annotations

from statistics import mean

from . import reports as rp

EASY_KINDS = {"easy", "long", "recovery"}
HARD_KINDS = {"tempo", "intervals", "race"}
# Garmin's own wording for its training effect scale
TE_LABELS = [(1.0, "No effect"), (2.0, "Minor"), (3.0, "Maintaining"), (4.0, "Improving"), (5.0, "Highly improving"), (99, "Overreaching")]


def check(cid: str, title: str, say: str, verdict: str) -> dict:
    return {"id": cid, "title": title, "say": say, "verdict": verdict}


def te_label(v: float) -> str:
    return next(l for top, l in TE_LABELS if v < top)


def build(conn, source: str, report: dict) -> list[dict]:
    out = []
    splits = [s for s in report.get("splits", []) if s.get("complete") and s.get("pace_s_per_km")]
    kind = (report.get("intent") or {}).get("kind")

    # Pacing: second half against the first, on complete kilometres
    if len(splits) >= 4:
        h = len(splits) // 2
        fade = mean(s["pace_s_per_km"] for s in splits[-h:]) - mean(s["pace_s_per_km"] for s in splits[:h])
        if fade <= -3:
            out.append(check("pacing", "Pacing", f"Faster second half ({round(-fade)} s/km quicker)", "good"))
        elif fade <= 5:
            out.append(check("pacing", "Pacing", "Even all the way", "good"))
        else:
            out.append(check("pacing", "Pacing", f"Slowed {round(fade)} s/km in the second half", "ok" if fade <= 15 else "low"))

    # Effort against what the run was meant to be
    zones = rp.hr_zones(conn)
    a = report["activity"]
    act = rp.activity_by_source_id(conn, source, a["source_id"]) if zones else None
    if act is not None:
        from .focus import zone_shares
        z = zone_shares(conn, act, zones["floors"])
        if z:
            hard = round(100 * z["hard"])
            if kind in EASY_KINDS:
                v = "good" if z["hard"] <= 0.1 else "ok" if z["hard"] <= 0.3 else "low"
                say = f"Easy, as meant ({hard}% in zones 4–5)" if v == "good" else f"Harder than an easy run ({hard}% in zones 4–5)"
            elif kind in HARD_KINDS:
                v = "good" if z["hard"] >= 0.3 else "ok"
                say = f"Hard, as a {kind} should be ({hard}% in zones 4–5)" if v == "good" else f"Easier than a {kind} ({hard}% in zones 4–5)"
            else:
                v, say = "info", f"{hard}% of the time in zones 4–5"
            out.append(check("effort", "Effort", say, v))

    # Cadence: level and how steady it stayed across kilometres
    cad = [s["cadence_spm"] for s in splits if s.get("cadence_spm")]
    if len(cad) >= 3:
        avg, spread = round(mean(cad)), max(cad) - min(cad)
        steady = spread <= 6
        v = "good" if steady and avg >= 165 else "ok"
        out.append(check("cadence", "Cadence", f"{'Steady' if steady else 'Varied'} at {avg} steps/min", v))

    # Heart-rate drift on steady runs
    dc = report.get("decoupling") or {}
    if dc.get("eligible") and dc.get("decoupling_pct") is not None:
        d = dc["decoupling_pct"]
        v = "good" if d <= 5 else "ok" if d <= 10 else "low"
        out.append(check("drift", "Heart-rate drift", f"{d:.1f}% ({'held steady' if v == 'good' else 'rose as you went'})", v))

    # Hills: where the climb cost time, using the flat-equivalent pace
    climb = a.get("elevation_gain_m") or 0
    if climb >= 30 and splits:
        hilly = max(splits, key=lambda s: (s.get("elevation_gain_m") or 0))
        if hilly.get("gap_pace_s_per_km") and (hilly.get("elevation_gain_m") or 0) >= 10:
            out.append(check("hills", "Hills", f"+{round(climb)} m · hilliest km {hilly['idx'] + 1}: {rp.fmt_pace(hilly['pace_s_per_km'])}"
                                               f" ({rp.fmt_pace(hilly['gap_pace_s_per_km'])} on the flat)", "info"))
        else:
            out.append(check("hills", "Hills", f"+{round(climb)} m in total", "info"))

    # Garmin's training effect, in Garmin's own words
    te = (report.get("garmin_metrics") or {}).get("aerobicTrainingEffect")
    if isinstance(te, (int, float)):
        lab = te_label(te)
        v = "low" if lab == "Overreaching" or (kind in EASY_KINDS and te >= 4) else "info"
        out.append(check("training_effect", "Training effect (Garmin)", f"{te:.1f} aerobic: {lab.lower()}"
                         + (" (a lot for an easy run)" if kind in EASY_KINDS and te >= 4 else ""), v))
    return out
