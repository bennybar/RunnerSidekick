"""How a run went, as a few plain checks, each with a verdict (good / ok / low) or "info" where there's nothing to
judge: pacing, effort against what the run was meant to be, cadence, aerobic decoupling (heart-rate drift), hills and Garmin's training
effect. Calculated from the run's report when the run is opened; no language model, and stored reports don't change."""

from __future__ import annotations

from statistics import mean

from . import reports as rp

EASY_KINDS = {"easy", "long", "recovery"}
EASY_SHARE = 0.7  # as in the weekly focus: an easy run spends at least 70% of its time below zone 3
HARD_KINDS = {"tempo", "threshold", "intervals", "race"}
STEADY_HARD_MAX = 0.3  # a steady aerobic run spends at most 30% of its time in zones 4–5
FADE_OK, HOT_FADE_OK = 15, 25        # s/km a second half may slow and still read "ok"; looser on a warm, humid day
DRIFT_GOOD, DRIFT_OK = 5, 10         # aerobic decoupling, %
HOT_DRIFT_GOOD, HOT_DRIFT_OK = 8, 13  # heat adds a few points at the same effort
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

    # Pacing: second half against the first, on complete kilometres, hill-adjusted where the samples allow it so a late
    # climb doesn't read as slowing
    if len(splits) >= 4:
        from .analytics import running as rn
        fade = rn.fade([s.get("gap_pace_s_per_km") or s["pace_s_per_km"] for s in splits])
        odd = rn.uneven_halves(splits)
        if odd:
            out.append(check("pacing", "Pacing", f"Halves not comparable: they climb differently ({100 * odd[0]:+.1f}% vs "
                                                 f"{100 * odd[1]:+.1f}% net grade)", "info"))
        elif fade < -rn.FADE_S_PER_KM:
            out.append(check("pacing", "Pacing", f"Faster second half ({round(-fade)} s/km quicker)", "good"))
        elif fade <= rn.FADE_S_PER_KM:
            out.append(check("pacing", "Pacing", "Even all the way", "good"))
        else:
            hot = (report.get("heat") or {}).get("hot")
            # Heat slows the same effort: on a warm, humid day the bar is looser, not gone
            out.append(check("pacing", "Pacing", f"Slowed {round(fade)} s/km in the second half" + (" (a warm, humid day)" if hot else ""),
                             "ok" if fade <= (HOT_FADE_OK if hot else FADE_OK) else "low"))

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
                # Easy means below zone 3, as everywhere else in the app (not merely "no zone 4–5")
                easy = round(100 * z["easy"])
                v = "good" if z["easy"] >= EASY_SHARE else "ok" if z["easy"] >= 0.5 and z["hard"] <= 0.1 else "low"
                say = f"Easy, as meant ({easy}% below zone 3)" if v == "good" else \
                    f"Harder than an easy run ({easy}% below zone 3, {hard}% in zones 4–5)"
            elif kind == "steady":
                v = "good" if z["hard"] <= STEADY_HARD_MAX else "ok" if z["hard"] <= 0.5 else "low"
                say = f"Steady, as meant ({hard}% in zones 4–5)" if v == "good" else f"Harder than steady aerobic ({hard}% in zones 4–5)"
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

    # Aerobic decoupling (heart-rate drift) on steady runs
    dc = report.get("decoupling") or {}
    if dc.get("eligible") and dc.get("decoupling_pct") is not None:
        d = dc["decoupling_pct"]
        hot = (report.get("heat") or {}).get("hot")
        # Heat raises heart rate at the same effort: on a hot, humid day the bars are looser, not gone
        good, ok = (HOT_DRIFT_GOOD, HOT_DRIFT_OK) if hot else (DRIFT_GOOD, DRIFT_OK)
        v = "good" if d <= good else "ok" if d <= ok else "low"
        out.append(check("drift", "Aerobic decoupling", f"{d:.1f}% ({'held steady' if v == 'good' else 'rose as you went'}"
                                                        f"{'; a warm, humid day raises it' if hot and d > DRIFT_GOOD else ''})", v))

    # Hills: where the climb cost time, using the flat-equivalent pace
    climb = a.get("elevation_gain_m") or 0
    vam = None
    act_row = rp.activity_by_source_id(conn, source, a["source_id"]) if climb >= 30 else None
    if act_row:
        from .numbers import climb_of
        c = climb_of(conn, act_row)
        vam = f" · best climb {c['vam']} m/h (+{c['gain_m']} m in {c['minutes']} min)" if c else None
    if climb >= 30 and splits:
        hilly = max(splits, key=lambda s: (s.get("elevation_gain_m") or 0))
        if hilly.get("gap_pace_s_per_km") and (hilly.get("elevation_gain_m") or 0) >= 10:
            out.append(check("hills", "Hills", f"+{round(climb)} m · hilliest km {hilly['idx'] + 1}: {rp.fmt_pace(hilly['pace_s_per_km'])}"
                                               f" ({rp.fmt_pace(hilly['gap_pace_s_per_km'])} on the flat)" + (vam or ""), "info"))
        else:
            out.append(check("hills", "Hills", f"+{round(climb)} m in total" + (vam or ""), "info"))

    # Conditions: the weather estimate, with whether it was hot enough to matter
    ht = report.get("heat")
    if ht:
        out.append(check("conditions", "Conditions (estimate)", ht["say"] + (" · warm and humid: heart rate runs higher" if ht["hot"] else ""),
                         "info"))

    # Garmin's training effect, in Garmin's own words
    te = (report.get("garmin_metrics") or {}).get("aerobicTrainingEffect")
    if isinstance(te, (int, float)):
        lab = te_label(te)
        v = "low" if lab == "Overreaching" or (kind in EASY_KINDS and te >= 4) else "info"
        out.append(check("training_effect", "Training effect (Garmin)", f"{te:.1f} aerobic: {lab.lower()}"
                         + (" (a lot for an easy run)" if kind in EASY_KINDS and te >= 4 else ""), v))
    return out
