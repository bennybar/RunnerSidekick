"""One run as a single Markdown file, built as a context packet for a language model as much as a page to read
(Runner Sidekick LLM Export v2). Three layers are kept apart: what the runner said, what the watch measured and the app
calculated, and what the app thinks it means. Every number names its source; anything missing is left out rather
than filled in. Tables instead of images, so it stays one plain file."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

import httpx

from . import reports as rp
from . import run_checks
from .db import one

SCHEMA = "Runner Sidekick LLM Export v2"
INTENT_WORDS = {"recovery": "Recovery", "easy": "Easy", "steady": "Steady aerobic", "long": "Long run", "tempo": "Tempo",
                "threshold": "Threshold", "intervals": "Intervals", "race": "Race", "progression": "Progression",
                "free": "Free run", "other": "Other"}
CLASS_WORDS = {"easy": "Easy-like", "tempo": "Tempo-like", "long": "Long run", "intervals": "Interval-like", "other": "Mixed effort"}
CONTEXT_WORDS = {
    "effort": {"very_easy": "Very easy", "easy": "Easy", "easy_moderate": "Easy-moderate", "moderate": "Moderate",
               "moderate_hard": "Moderate-hard", "hard": "Hard", "very_hard": "Very hard"},
    "feel": {"great": "Great", "good": "Good", "okay": "Okay", "poor": "Poor", "very_poor": "Very poor"},
    "limiter": {"none": "None", "cardio": "Cardio", "breathing": "Breathing", "legs": "Legs", "feet": "Feet",
                "muscular_fatigue": "Muscular fatigue", "heat": "Heat", "humidity": "Humidity", "hills": "Hills",
                "illness": "Illness", "pain": "Pain", "gi": "GI (stomach)", "motivation": "Motivation", "other": "Other"},
    "health": {"normal": "Normal", "recovering": "Recovering from illness", "mild_symptoms": "Mild symptoms",
               "poor_sleep": "Poor sleep", "fatigued": "Fatigued", "sore": "Sore", "other": "Other"},
}


def word(field: str, v: str | None) -> str | None:
    if not v:
        return None
    return CONTEXT_WORDS.get("limiter" if field == "limiter2" else field, {}).get(v, v.replace("_", " ").capitalize())


def clock(sec: float | None) -> str:
    if sec is None:
        return "–"
    t = round(sec)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def pace(s_per_km: float | None) -> str:
    return rp.fmt_pace(s_per_km) if s_per_km else "–"


def num(v, fmt: str = "{:.0f}", unit: str = "") -> str:
    return "–" if v is None else fmt.format(v) + unit


def signed(v: float, fmt: str = "{:+.0f}", unit: str = "") -> str:
    s = fmt.format(v)
    return (s.lstrip("+-") if not s.strip("+-0.") else s.replace("-", "−")) + unit  # no sign on a zero


def zone_table(conn, a: dict) -> list[str]:
    zones = rp.hr_zones(conn)
    s = rp.samples_for(conn, a["id"])
    if not zones or s is None:
        return []
    from .analytics import insights as ins
    r = ins.RunData(a["source_id"], a["local_date"], datetime.min, None, a["distance_m"], a["moving_s"], None, s, [], "steady")
    zt = ins.zone_time(r, zones["floors"])
    total = sum(zt)
    if not total:
        return []
    f = [round(x) for x in zones["floors"]]
    names = [f"Below zone 1 · < {f[0]} bpm", f"Zone 1 · {f[0]}–{f[1] - 1} bpm", f"Zone 2 · {f[1]}–{f[2] - 1} bpm",
             f"Zone 3 · {f[2]}–{f[3] - 1} bpm", f"Zone 4 · {f[3]}–{f[4] - 1} bpm", f"Zone 5 · ≥ {f[4]} bpm"]
    rows = ["| Zone | Time | Share |", "|---|---:|---:|"]
    for k in range(5, -1, -1):
        if zt[k] or k > 0:
            rows.append(f"| {names[k]} | {clock(zt[k])} | {100 * zt[k] / total:.0f}% |")
    return rows + ["", f"Zones from Garmin ({zones.get('method') or 'heart-rate zones'}, max HR {zones.get('max_hr', '–')}); "
                       "a training guide, not a physiological measurement."]


def halves(s, values: list | None) -> tuple[float, float] | None:
    """Time-weighted means over the first and second half of moving time (stops left out)."""
    from .analytics.running import _weights
    if s is None or not values:
        return None
    w = _weights(s)
    total = sum(x for x in w if x > 0)
    acc, out = 0.0, [[0.0, 0.0], [0.0, 0.0]]
    for i, wi in enumerate(w):
        if wi <= 0:
            continue
        h = 0 if acc < total / 2 else 1
        acc += wi
        if values[i] is not None:
            out[h][0] += wi * values[i]
            out[h][1] += wi
    if not out[0][1] or not out[1][1] or min(out[0][1], out[1][1]) < 0.5 * total / 2:
        return None  # too little of either half measured
    return out[0][0] / out[0][1], out[1][0] / out[1][1]


def minute_table(conn, a: dict) -> list[str]:
    """One row per minute: distance, pace over that minute, average heart rate, cadence, power and elevation. Averages are
    time-weighted (pace, cadence and power over moving time only), so irregular sampling doesn't tilt them."""
    s = rp.samples_for(conn, a["id"])
    if s is None or not s.t:
        return []
    power = s.power is not None and any(p for p in s.power)
    rows = ["| Min | km | Pace | HR | Cadence |" + (" Power |" if power else "") + " Elevation |",
            "|---:|---:|---:|---:|---:|" + ("---:|" if power else "") + "---:|"]
    t0 = s.t[0]
    buckets: dict[int, list[int]] = {}
    for i, t in enumerate(s.t):
        buckets.setdefault(int((t - t0) // 60), []).append(i)

    from .analytics.running import _weights
    moving = _weights(s)
    held = [min(s.t[i + 1] - s.t[i], 10.0) if i + 1 < len(s.t) else 1.0 for i in range(len(s.t))]  # how long each sample stands for

    def mean(values, idx, w):
        pts = [(w[i], values[i]) for i in idx if values[i] is not None and w[i] > 0]
        tw = sum(a for a, _ in pts)
        return sum(a * v for a, v in pts) / tw if tw else None
    for m in sorted(buckets):
        idx = buckets[m]
        d = [s.dist[i] for i in idx if s.dist[i] is not None]
        spd = mean(s.speed, idx, moving)
        rows.append(f"| {m + 1} | {num(d[-1] / 1000 if d else None, '{:.2f}')} | {pace(1000 / spd if spd else None)} | "
                    f"{num(mean(s.hr, idx, held))} | {num(mean(s.cad, idx, moving))} | "
                    + (f"{num(mean(s.power, idx, moving), unit=' W')} | " if power else "")
                    + f"{num(mean(s.elev, idx, held), '{:.0f}', ' m')} |")
    return rows


def recovery_context(conn, source: str, a: dict, s) -> list[tuple[str, str]]:
    """Garmin's readings from the morning of the run, only those that exist."""
    day = a["local_date"]
    rows = {r["metric"]: r for r in conn.daily_observation.find({"source": source, "local_date": day, "state": "measured"},
                                                                {"_id": 0, "metric": 1, "value": 1, "label": 1})}
    out = []

    def v(m):
        return rows[m]["value"] if m in rows and rows[m].get("value") is not None else None
    if v("resting_hr") is not None:
        out.append(("Resting HR", f"{v('resting_hr'):.0f} bpm"))
    if v("hrv_overnight_avg") is not None:
        lab = (rows["hrv_overnight_avg"].get("label") or "").replace("_", " ").lower()
        out.append(("HRV last night", f"{v('hrv_overnight_avg'):.0f} ms" + (f" ({lab})" if lab else "")))
    if v("hrv_weekly_avg") is not None:
        out.append(("HRV 7-day average", f"{v('hrv_weekly_avg'):.0f} ms"))
    if v("sleep_duration") is not None:
        sl = round(v("sleep_duration") / 60)
        out.append(("Sleep", f"{sl // 60} h {sl % 60:02d} min"))
    if v("garmin_sleep_score") is not None:
        out.append(("Sleep score", f"{v('garmin_sleep_score'):.0f}"))
    if v("garmin_training_readiness") is not None:
        lab = (rows["garmin_training_readiness"].get("label") or "").replace("_", " ").lower()
        out.append(("Training readiness (Garmin)", f"{v('garmin_training_readiness'):.0f} / 100" + (f" ({lab})" if lab else "")))
    bb = [x for x in ((s.dyn or {}).get("bb") or []) if x is not None] if s is not None else []
    if bb:
        out.append(("Body Battery", f"{bb[0]:.0f} at the start → {bb[-1]:.0f} at the end"))
    return out


def similar_details(conn, source: str, comp: dict) -> list[dict]:
    """Each similar run with its power, cadence and drift, for the comparison table and the deltas."""
    out = []
    for c in comp.get("runs") or []:
        act = rp.activity_by_source_id(conn, source, c["source_id"])
        if act is None:
            continue
        dc = rp.run_analysis(conn, act)["decoupling"]
        out.append({**c, "power": (act.get("garmin_metrics") or {}).get("avgPower"), "cadence": act.get("avg_cadence_spm"),
                    "drift": dc.get("decoupling_pct") if dc.get("eligible") else None})
    return out


def med(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else None


def markdown(conn, source: str, sid: str, app_version: str | None = None, now: datetime | None = None,
             fetch=httpx.get) -> tuple[str, str] | None:
    """(file name, Markdown text) for one run, or None when the run isn't there."""
    a = rp.activity_by_source_id(conn, source, sid)
    r = rp.build_post_run(conn, source, sid, False) if a else None
    if not a or not r:
        return None
    off = timedelta(seconds=a["utc_offset_s"] or 0)
    start = datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")).astimezone(timezone(off))
    end = start + timedelta(seconds=a["elapsed_s"] or 0)
    g = r.get("garmin_metrics") or {}
    intent = r.get("intent") or {}
    said = intent if intent.get("source") == "user" else {}
    cl = r.get("classified") or {}
    s = rp.samples_for(conn, a["id"])
    dc = r.get("decoupling") or {}
    from . import weather
    wx = weather.for_run(conn, a, fetch)
    name = a.get("name") if a.get("name") and a["name"].strip().lower() not in ("running", "run") else None
    km = (a["distance_m"] or 0) / 1000
    L: list[str] = []
    add = L.append

    # 1–2. Title and the basic run summary
    add(f"# Running{' · ' + name if name else ''}")
    add(f"**{start.strftime('%A %-d %B %Y')}**  ")
    add(f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')} (UTC{start.strftime('%z')[:3]}:{start.strftime('%z')[3:]})  ")
    add("")
    add(f"Distance: **{num(km, '{:.2f}', ' km')}**  ")
    add(f"Moving time: **{clock(a['moving_s'])}** · Elapsed: **{clock(a['elapsed_s'])}**  ")
    if a.get("elapsed_s") and a.get("moving_s") is not None:
        still = max(0.0, a["elapsed_s"] - a["moving_s"])
        paused = max(0.0, a["elapsed_s"] - (a.get("timer_s") or a["elapsed_s"]))
        add(f"Not moving: **{clock(still)}**" + (f" (timer paused {clock(paused)})" if paused >= 1 else "") + "  ")
    add(f"Pace (moving): **{pace(r.get('pace_moving_s_per_km'))}**  ")
    add(f"Heart rate: **{num(a.get('avg_hr'), unit=' bpm')}** average · **{num(a.get('max_hr'), unit=' bpm')}** max  ")
    add(f"Elevation: **+{num(a.get('elevation_gain_m'), unit=' m')}** / −{num(a.get('elevation_loss_m'), unit=' m')}  ")
    if r.get("garmin_vo2max_day"):
        add(f"VO₂ max (Garmin estimate): **{r['garmin_vo2max_day']['value']:.1f}**  ")
    add("")
    if said:
        add(f"User intent: **{INTENT_WORDS.get(said['kind'], said['kind'])}**  ")
    elif intent.get("source") == "plan":
        add(f"Planned as: **{INTENT_WORDS.get(intent['kind'], intent['kind'])}** (from the day's plan)  ")
    if cl.get("kind"):
        add(f"Data-based classification: **{CLASS_WORDS.get(cl['kind'], cl['kind'])}**"
            + (" (for reference only; the runner's intent comes first)" if said else "") + "  ")
        if cl.get("confidence"):
            add(f"Classification confidence: **{cl['confidence'].capitalize()}** · {cl.get('reason')}  ")
    add("")

    # 3. Athlete context: only what the runner entered
    told = [("Intent", INTENT_WORDS.get(said["kind"], said["kind"]) if said else None), ("Target", said.get("target")),
            ("Perceived effort", word("effort", said.get("effort"))), ("Overall feel", word("feel", said.get("feel"))),
            ("Primary limiter", word("limiter", said.get("limiter"))), ("Secondary limiter", word("limiter2", said.get("limiter2"))),
            ("Health status", word("health", said.get("health"))), ("Notes", (said.get("note") or "").strip().rstrip(".") or None)]
    if said:
        add("## Athlete context")
        add("As entered by the runner.  ")
        L.extend(f"{k}: **{v}**  " for k, v in told if v)
        add("")

    # 4. How it went
    checks = run_checks.build(conn, source, r)
    if checks:
        add("## How it went")
        add("| Check | Result | Verdict |")
        add("|---|---|---|")
        for c in checks:
            add(f"| {c['title']} | {c['say']} | {dict(good='Good', ok='OK', low='Low').get(c['verdict'], 'Info')} |")
        add("")
        add("Checks by Runner Sidekick, judged against " + ("the runner's intent." if said else "the run's type."))
        add("")

    # 5. Conditions
    if wx:
        add("## Conditions")
        add(f"Temperature: **{wx['temperature_2m']:.0f}°C**  ")
        for key, label, unit in (("relative_humidity_2m", "Humidity", "%"), ("dew_point_2m", "Dew point", "°C"),
                                 ("wind_speed_10m", "Wind", " km/h"), ("apparent_temperature", "Feels like", "°C")):
            if wx.get(key) is not None:
                add(f"{label}: **{wx[key]:.0f}{unit}**  ")
        add(f"Weather source: **{wx['source']}**, an estimate for the start area (to about 1 km) at "
            f"{datetime.fromisoformat(wx['hour_utc'].replace('Z', '+00:00')).astimezone(timezone(off)).strftime('%H:%M')}; "
            "not recorded by the watch.")
        add("")

    # 6. Heart-rate zones
    zt = zone_table(conn, a)
    if zt:
        add("## Heart-rate zones")
        L.extend(zt)
        add("")

    # 7. Pace and splits
    splits = r.get("splits") or []
    if splits:
        full = [x for x in splits if x.get("complete") and x.get("pace_s_per_km")]
        add("## Pace and splits")
        if full:
            best = min(full, key=lambda x: x["pace_s_per_km"])
            h = len(full) // 2
            add(f"Best km: **{pace(best['pace_s_per_km'])}** (km {best['idx'] + 1})  ")
            if h:
                first = sum(x["pace_s_per_km"] for x in full[:h]) / h
                second = sum(x["pace_s_per_km"] for x in full[-h:]) / h
                add(f"First half: **{pace(first)}** · Second half: **{pace(second)}** ({signed(second - first, unit=' s/km')})  ")
            hilly = max(full, key=lambda x: x.get("elevation_gain_m") or 0)
            if (hilly.get("elevation_gain_m") or 0) >= 10 and hilly.get("gap_pace_s_per_km"):
                add(f"Hilliest km: **km {hilly['idx'] + 1}**, +{hilly['elevation_gain_m']:.0f} m: **{pace(hilly['pace_s_per_km'])}** "
                    f"actual, **{pace(hilly['gap_pace_s_per_km'])}** flat-equivalent  ")
            add("")
        descent = any(x.get("elevation_loss_m") is not None for x in splits)
        add("| Km | Pace | Flat-equivalent | HR | Zone | Cadence | Climb |" + (" Descent |" if descent else ""))
        add("|---:|---:|---:|---:|---|---:|---:|" + ("---:|" if descent else ""))
        for x in splits:
            add(f"| {x['idx'] + 1}{'' if x.get('complete') else '*'} | {pace(x.get('pace_s_per_km'))} | {pace(x.get('gap_pace_s_per_km'))} | "
                f"{num(x.get('avg_hr'))} | {('Z' + str(x['zone'])) if x.get('zone') else '–'} | {num(x.get('cadence_spm'))} | "
                f"+{num(x.get('elevation_gain_m'), unit=' m')} |" + (f" −{num(x.get('elevation_loss_m'), unit=' m')} |" if descent else ""))
        add("")
        add("Flat-equivalent: the pace this effort would give on flat ground (Runner Sidekick, Minetti's energy cost of "
            "running on slopes). * Partial km.")
        add("")

    # 8. Decoupling, with the numbers behind it
    add("## Aerobic decoupling (heart-rate drift)")
    f1, f2 = dc.get("first_half") or {}, dc.get("second_half") or {}
    if dc.get("decoupling_pct") is not None and f1 and f2:
        add(f"Warm-up excluded: **first 10 min of moving time** · Analysed: **{clock(dc.get('segment_moving_s'))}**, "
            "split into equal-duration halves  ")
        add("")
        add("| Metric | First half | Second half | Change |")
        add("|---|---:|---:|---:|")
        add(f"| Heart rate | {f1['mean_hr']:.0f} bpm | {f2['mean_hr']:.0f} bpm | {signed(f2['mean_hr'] - f1['mean_hr'], unit=' bpm')} |")
        p1, p2 = 1000 / f1["mean_speed_mps"], 1000 / f2["mean_speed_mps"]
        add(f"| {'Hill-adjusted pace' if dc.get('grade_adjusted') else 'Pace'} | {pace(p1)} | {pace(p2)} | {signed(p2 - p1, unit=' s/km')} |")
        if dc.get("power_first_half_w") is not None:
            add(f"| Power | {dc['power_first_half_w']} W | {dc['power_second_half_w']} W | "
                f"{signed(dc['power_second_half_w'] - dc['power_first_half_w'], unit=' W')} |")
        add("")
        add(f"Pace:HR decoupling: **{dc['decoupling_pct']:.1f}%**  ")
        if dc.get("power_decoupling_pct") is not None:
            add(f"Power:HR decoupling: **{dc['power_decoupling_pct']:.1f}%**  ")
        else:
            add("Power:HR decoupling: not available (no running power recorded)  ")
        add("")
        on_hills = any(x.startswith("hilly") for x in dc.get("reasons") or [])
        add("Interpretation: under 5% generally indicates stable aerobic coupling for this run (a coaching heuristic, not a "
            "validated threshold)." + (" Hilly route: power:HR is the better read here." if on_hills and dc.get("power_decoupling_pct") is not None else "")
            + ("" if dc.get("eligible") else " Indicative only: " + "; ".join(dc.get("reasons") or []) + "."))
    else:
        add("Not calculated: " + "; ".join(dc.get("reasons") or ["not enough heart-rate data"]) + ".")
    add("")

    # 9. Running dynamics: Garmin's averages, with the halves from the samples
    dyn = (s.dyn or {}) if s is not None else {}
    rows = []
    for label, avg, mx, series_, fmt, unit in (
            ("Power", g.get("avgPower"), g.get("maxPower"), s.power if s is not None else None, "{:.0f}", " W"),
            ("Normalized power", g.get("normPower"), None, None, "{:.0f}", " W"),
            ("Cadence", a.get("avg_cadence_spm"), g.get("maxRunningCadenceInStepsPerMinute"), s.cad if s is not None else None, "{:.0f}", " spm"),
            ("Step length", g["avgStrideLength"] / 100 if g.get("avgStrideLength") else None, None, dyn.get("stride"), "{:.2f}", " m"),
            ("Vertical oscillation", g.get("avgVerticalOscillation"), None, dyn.get("vo"), "{:.1f}", " cm"),
            ("Vertical ratio", g.get("avgVerticalRatio"), None, dyn.get("vr"), "{:.1f}", "%"),
            ("Ground contact time", g.get("avgGroundContactTime"), None, dyn.get("gct"), "{:.0f}", " ms")):
        hv = halves(s, series_)
        if avg is None and hv is None:
            continue
        rows.append(f"| {label} | {num(avg, fmt, unit)} | {num(mx, fmt, unit) if mx else '–'} | "
                    + (f"{fmt.format(hv[0])}{unit} | {fmt.format(hv[1])}{unit} |" if hv else "– | – |"))
    if rows:
        add("## Running dynamics")
        add("| Metric | Average | Max | First half | Second half |")
        add("|---|---:|---:|---:|---:|")
        L.extend(rows)
        add("")
        add("Averages and maxima from Garmin; halves are equal halves of moving time, from the watch's samples.")
        add("")

    # 11. Recovery context (no reliable heart-rate recovery after the stop, so that section is left out)
    rc = recovery_context(conn, source, a, s)
    if rc:
        add("## Recovery context")
        add("Garmin's readings for the day of the run; context, not a diagnosis.  ")
        L.extend(f"{k}: **{v}**  " for k, v in rc)
        add("")

    # 12. Best efforts
    efforts = list((r.get("best_efforts") or {}).values())
    if efforts:
        add("## Best efforts in this run")
        add("| Distance | Time | Pace | Your best before |")
        add("|---|---:|---:|---:|")
        for e in efforts:
            add(f"| {e['label']} | {clock(e['elapsed_s'])}{' (new best)' if e.get('is_best') else ''} | {pace(e.get('pace_s_per_km'))} | "
                f"{clock(e.get('previous_best_s'))} |")
        add("")

    # 13. Similar runs, with this run against their median
    comp = r.get("comparable") or {}
    sims = similar_details(conn, source, comp) if comp.get("runs") else []
    if sims:
        add(f"## Similar runs ({comp['n']})")
        cr = comp.get("criteria") or {}
        lo, hi = cr.get("distance_ratio") or [0.8, 1.2]
        add(f"Criteria: same sport, distance {lo:.0%}–{hi:.0%} of this run, climbing within ±{cr.get('gain_per_km_tolerance', 8):.0f} m/km, "
            "steady effort, earlier runs in the last 120 days.")
        add("")
        deltas = []
        mp = med([x.get("pace_s_per_km") for x in sims])
        if mp and r.get("pace_moving_s_per_km"):
            d = r["pace_moving_s_per_km"] - mp
            deltas.append(f"Pace: **{abs(d):.0f} s/km {'faster' if d < 0 else 'slower'} than the median**" if abs(d) >= 1 else "Pace: **about the median**")
        for label, mine, theirs, unit, better_low in (
                ("Average HR", a.get("avg_hr"), med([x.get("avg_hr") for x in sims]), " bpm", None),
                ("Power", g.get("avgPower"), med([x["power"] for x in sims]), " W", None),
                ("Cadence", a.get("avg_cadence_spm"), med([x["cadence"] for x in sims]), " spm", None),
                ("Aerobic decoupling (pace:HR)", dc.get("decoupling_pct") if dc.get("eligible") else None, med([x["drift"] for x in sims]), " points", True)):
            if mine is not None and theirs is not None:
                d = mine - theirs
                deltas.append(f"{label}: **{signed(d, '{:+.1f}' if unit == ' points' else '{:+.0f}', unit)}**"
                              + (f" ({'better' if d < 0 else 'worse'})" if better_low and abs(d) >= 0.5 else ""))
        if deltas:
            add("### Compared with the median of these runs")
            L.extend(f"{x}  " for x in deltas)
            add("")
        add("| Date | Distance | Pace | HR | Power | Decoupling | Cadence |")
        add("|---|---:|---:|---:|---:|---:|---:|")
        add(f"| **This run** | {num(km, '{:.2f}', ' km')} | {pace(r.get('pace_moving_s_per_km'))} | {num(a.get('avg_hr'))} | "
            f"{num(g.get('avgPower'), unit=' W')} | {num(dc.get('decoupling_pct') if dc.get('eligible') else None, '{:.1f}', '%')} | "
            f"{num(a.get('avg_cadence_spm'))} |")
        for c in sims:
            add(f"| {c['local_date']} | {num((c.get('distance_m') or 0) / 1000, '{:.2f}', ' km')} | {pace(c.get('pace_s_per_km'))} | "
                f"{num(c.get('avg_hr'))} | {num(c['power'], unit=' W')} | {num(c['drift'], '{:.1f}', '%')} | {num(c['cadence'])} |")
        add("")

    # 14. Recent trend: the fitness progress signals (need enough comparable runs, or they say so)
    from . import progress
    today = (now or datetime.now(timezone(off))).date()
    pg = progress.build(conn, source, today)
    known = [x for x in pg["signals"] if x["direction"]]
    if known:
        add("## Recent trend")
        add(f"As of {today.isoformat()}, across recent runs (Runner Sidekick): **{pg['verdict']}**"
            + (f", {pg['confidence']} confidence" if pg.get("confidence") else "") + ".  ")
        add("")
        add("| Signal | Direction | Numbers |")
        add("|---|---|---|")
        for x in pg["signals"]:
            dirn = "dipped (device estimate)" if x["id"] == "vo2" and x["direction"] == "declining" else x["direction"] or "not enough data"
            add(f"| {x['title']} | {dirn} | {x['say']} |")
        add("")

    # 15. Garmin's numbers
    if g:
        lines = []
        for key, label, fmt in (("aerobicTrainingEffect", "Aerobic training effect", "{:.1f}"),
                                ("anaerobicTrainingEffect", "Anaerobic training effect", "{:.1f}"),
                                ("trainingEffectLabel", "Training effect", None), ("activityTrainingLoad", "Training load", "{:.0f}"),
                                ("calories", "Calories", "{:.0f}")):
            v = g.get(key)
            if v is not None:
                lines.append(f"{label}: **{(fmt.format(v) if fmt and isinstance(v, (int, float)) else str(v).replace('_', ' ').title())}**  ")
        if lines:
            add("## From Garmin")
            L.extend(lines)
            add("")

    # 16. The week
    wk = r.get("calendar_week") or {}
    if wk:
        add("## The week")
        add(f"{wk.get('start')} to {wk.get('end')}: **{wk.get('runs', 0)} run{'' if wk.get('runs') == 1 else 's'}**, "
            f"{num((wk.get('distance_m') or 0) / 1000, '{:.1f}', ' km')}, {clock(wk.get('moving_s'))} moving, "
            f"+{num(wk.get('elevation_gain_m'), unit=' m')} climb.")
        add("")

    # 17. Next focus
    if r.get("next_focus"):
        add("## Next focus")
        add(r["next_focus"])
        add("")
        add("A rule-based suggestion by Runner Sidekick, " + ("based on the runner's intent." if said else "based on the data."))
        add("")

    # 18. AI input: facts and context for a model to reason from, then the app's own reading, kept apart
    add("## AI input")
    add("### Athlete intent")
    if said:
        add(f"{INTENT_WORDS.get(said['kind'], said['kind'])} run" + (f", target: {said['target']}." if said.get("target") else "."))
    elif intent.get("source") == "plan":
        add(f"Not stated by the runner; the day's plan said {INTENT_WORDS.get(intent['kind'], intent['kind']).lower()}.")
    else:
        add("Not stated by the runner." + (f" The data looks {CLASS_WORDS.get(cl['kind'], cl['kind']).lower()} "
                                           f"({cl.get('confidence', 'low')} confidence)." if cl.get("kind") else ""))
    add("")
    subj = [f"{k}: {v}." for k, v in told[2:] if v]
    add("### Subjective report")
    add(" ".join(subj) if subj else "None given.")
    add("")
    add("### Objective highlights")
    hl = [f"{km:.2f} km in {clock(a['moving_s'])} moving at {pace(r.get('pace_moving_s_per_km'))}."]
    if a.get("avg_hr"):
        hl.append(f"Average HR {a['avg_hr']:.0f} bpm, max {num(a.get('max_hr'))} bpm.")
    if a.get("elevation_gain_m"):
        hl.append(f"{a['elevation_gain_m']:.0f} m climbing, {num(a.get('elevation_loss_m'))} m descent.")
    if dc.get("decoupling_pct") is not None:
        hl.append(f"Pace:HR decoupling {dc['decoupling_pct']:.1f}%" + (f", power:HR {dc['power_decoupling_pct']:.1f}%" if dc.get("power_decoupling_pct") is not None else "")
                  + ("." if dc.get("eligible") else " (indicative only)."))
    hl += [f"{c['title']}: {c['say']}." for c in checks if c["id"] in ("pacing", "effort", "cadence", "hills")]
    if g.get("aerobicTrainingEffect") is not None:
        hl.append(f"Garmin aerobic training effect: {g['aerobicTrainingEffect']:.1f}.")
    hl += [f"New best {e['label']}: {clock(e['elapsed_s'])}." for e in efforts if e.get("is_best")]
    L.extend(f"- {x}" for x in hl)
    add("")
    ctx = []
    if said.get("health") and said["health"] != "normal":
        ctx.append(f"Health status reported by the runner: {word('health', said['health']).lower()}.")
    if wx:
        ctx.append(f"Weather estimate: {wx['temperature_2m']:.0f}°C" + (f", dew point {wx['dew_point_2m']:.0f}°C" if wx.get("dew_point_2m") is not None else "") + ".")
    ctx += [f"{k} (that day): {v}." for k, v in rc]
    if wk:
        ctx.append(f"Week of the run: {wk.get('runs', 0)} run{'' if wk.get('runs') == 1 else 's'}, {(wk.get('distance_m') or 0) / 1000:.1f} km.")
    if sims:
        ctx.append(f"{len(sims)} similar earlier runs to compare with (table above).")
    if known:
        ctx.append(f"Recent fitness trend: {pg['verdict']}.")
    if ctx:
        add("### Context")
        L.extend(f"- {x}" for x in ctx)
        add("")
    qs = []
    if said:
        qs.append(f"Did the run match its intent ({INTENT_WORDS.get(said['kind'], said['kind']).lower()}"
                  + (f", {said['target']}" if said.get("target") else "") + ")?")
    if len(sims) >= 3:
        qs.append("Against similar runs, is aerobic efficiency (pace or power at the same heart rate) improving?")
    if dc.get("decoupling_pct") is not None:
        qs.append("Was the heart-rate drift meaningful, given the warm-up exclusion, terrain and conditions?")
    if dyn or (s is not None and s.power):
        qs.append("Did running mechanics (cadence, ground contact, stride, power) change late in the run?")
    if said.get("limiter") and said["limiter"] != "none":
        qs.append(f"What does the data say about the reported limiter ({word('limiter', said['limiter']).lower()}): was it cardiovascular or mechanical?")
    if said.get("health") and said["health"] != "normal":
        qs.append("How does this run fit with the reported health status?")
    if wx and ((wx.get("dew_point_2m") or 0) >= 16 or wx["temperature_2m"] >= 24):
        qs.append("How much did heat and humidity add to heart rate?")
    qs.append("What should be watched on the next comparable run?")
    add("### Questions worth considering")
    L.extend(f"- {q}" for q in qs)
    add("")

    add("## App-generated interpretation")
    ok = one(conn.run_ai, {"source_id": sid, "status": "ok"}, sort=[("id", -1)])  # the newest AI input that passed its checks
    if ok:
        o = ok["output"]
        add(f"Interpretation, not source data: written by AI ({ok['model']}) on {ok['created_at'][:10]} from the app's analysis "
            "(the runner's notes are never sent). Guidance, not medical advice.")
        add("")
        if o.get("tldr"):
            add(f"**TL;DR:** {o['tldr']}")
            add("")
        if o.get("summary"):
            add(o["summary"])
            add("")
        for title, key in (("Went well", "went_well"), ("To work on", "to_work_on")):
            if o.get(key):
                add(f"### {title}")
                L.extend(f"- {p['text']}" for p in o[key])
                add("")
        nt = o.get("next_time") or {}
        if nt.get("text"):
            add(f"### Next time ({nt.get('direction', 'same')})")
            add(nt["text"])
            add("")
    else:
        add("No AI interpretation for this run yet.")
        add("")

    # 19. Minute by minute, folded where Markdown viewers support it
    mt = minute_table(conn, a)
    if mt:
        add("## Minute by minute")
        add("<details>")
        add("<summary>Minute-by-minute data</summary>")
        add("")
        L.extend(mt)
        add("")
        add("</details>")
        add("")

    # 20. Data provenance
    add("## Data provenance")
    prov = [("Activity source", "Garmin Connect (watch recording)"),
            ("Heart rate, pace, cadence, elevation", "Garmin watch samples"),
            ("Power and running dynamics", "Garmin" if g.get("avgPower") or dyn else None),
            ("VO₂ max, training effect, training load, HR zones", "Garmin"),
            ("Recovery context", "Garmin daily data" if rc else None),
            ("Weather", f"{wx['source']} (external estimate)" if wx else None),
            ("Athlete context", "Entered by the runner" if said else None),
            ("Flat-equivalent pace, decoupling, checks, classification, similar runs, trend, next focus", "Runner Sidekick calculation"),
            ("App-generated interpretation", f"AI ({ok['model']}) from Runner Sidekick's analysis" if ok else None)]
    L.extend(f"{k}: **{v}**  " for k, v in prov if v)
    add("")

    # 21. Schema and version
    stamp = (now or datetime.now(timezone(off))).replace(microsecond=0)
    add(f"Export schema: **{SCHEMA}**  ")
    if app_version:
        add(f"App version: **{app_version}**  ")
    add(f"Exported: **{stamp.isoformat()}**")

    file_name = f"{start.strftime('%Y-%m-%d-%H%M%S')}-running.md"  # the same name the app gives the file
    return file_name, "\n".join(L) + "\n"
