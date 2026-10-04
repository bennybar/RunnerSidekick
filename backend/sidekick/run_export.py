"""One run as a single Markdown file: everything the app knows about it (summary, how it went, heart-rate zones,
pace, splits, best efforts, drift, elevation, similar runs, Garmin's numbers, the week, a minute-by-minute table) and
the AI input at the end. Laid out like HealthFit's export, with tables instead of images so it stays one file."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import reports as rp
from . import run_checks
from .db import one

INTENT_WORDS = {"easy": "Easy", "long": "Long", "tempo": "Tempo", "intervals": "Intervals", "race": "Race", "recovery": "Recovery"}


def clock(sec: float | None) -> str:
    if sec is None:
        return "–"
    t = round(sec)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def pace(s_per_km: float | None) -> str:
    return rp.fmt_pace(s_per_km) if s_per_km else "–"


def num(v, fmt: str = "{:.0f}", unit: str = "") -> str:
    return "–" if v is None else fmt.format(v) + unit


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
    rows = ["| Zone | Time | Share |", "|---|---|---|"]
    for k in range(5, -1, -1):
        if zt[k] or k > 0:
            rows.append(f"| {names[k]} | {clock(zt[k])} | {100 * zt[k] / total:.0f}% |")
    return rows + ["", f"Zones from Garmin ({zones.get('method') or 'heart-rate zones'}, max HR {zones.get('max_hr', '–')})."]


def minute_table(conn, a: dict) -> list[str]:
    """One row per moving minute: distance, pace over that minute, average heart rate, cadence and elevation."""
    s = rp.samples_for(conn, a["id"])
    if s is None or not s.t:
        return []
    rows = ["| Min | km | Pace | HR | Cadence | Elevation |", "|---|---|---|---|---|---|"]
    t0 = s.t[0]
    buckets: dict[int, list[int]] = {}
    for i, t in enumerate(s.t):
        buckets.setdefault(int((t - t0) // 60), []).append(i)

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None
    for m in sorted(buckets):
        idx = buckets[m]
        d = [s.dist[i] for i in idx if s.dist[i] is not None]
        spd = mean([s.speed[i] for i in idx])
        rows.append(f"| {m + 1} | {num(d[-1] / 1000 if d else None, '{:.2f}')} | {pace(1000 / spd if spd else None)} | "
                    f"{num(mean([s.hr[i] for i in idx]))} | {num(mean([s.cad[i] for i in idx]))} | {num(mean([s.elev[i] for i in idx]), '{:.0f}', ' m')} |")
    return rows


def markdown(conn, source: str, sid: str, app_version: str | None = None) -> tuple[str, str] | None:
    """(file name, Markdown text) for one run, or None when the run isn't there."""
    a = rp.activity_by_source_id(conn, source, sid)
    r = rp.build_post_run(conn, source, sid, False) if a else None
    if not a or not r:
        return None
    start = datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=a["utc_offset_s"] or 0)
    end = start + timedelta(seconds=a["elapsed_s"] or 0)
    g = r.get("garmin_metrics") or {}
    intent = r.get("intent") or {}
    name = a.get("name") if a.get("name") and a["name"].strip().lower() not in ("running", "run") else None
    L: list[str] = []
    add = L.append

    add(f"# Running{' · ' + name if name else ''}")
    add(f"**{start.strftime('%A %-d %B %Y')}**  ")
    add(f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}  ")
    if intent.get("kind"):
        add(f"Run type: **{INTENT_WORDS.get(intent['kind'], intent['kind'].title())}**"
            f"{' (inferred from pace and heart rate)' if intent.get('source') == 'inferred' else ''}  ")
    add(f"Distance: **{num((a['distance_m'] or 0) / 1000, '{:.2f}', ' km')}**  ")
    add(f"Moving time: **{clock(a['moving_s'])}** · Elapsed: **{clock(a['elapsed_s'])}**  ")
    add(f"Pace (moving): **{pace(r.get('pace_moving_s_per_km'))}**  ")
    add(f"Heart rate: **{num(a.get('avg_hr'), unit=' bpm')}** average · **{num(a.get('max_hr'), unit=' bpm')}** max  ")
    add(f"Elevation: **+{num(a.get('elevation_gain_m'), unit=' m')}** / −{num(a.get('elevation_loss_m'), unit=' m')}  ")
    if r.get("garmin_vo2max_day"):
        add(f"VO₂ max (Garmin): **{r['garmin_vo2max_day']['value']:.1f}**  ")
    add("")

    checks = run_checks.build(conn, source, r)
    if checks:
        add("## How it went")
        add("| Check | Result | Verdict |")
        add("|---|---|---|")
        for c in checks:
            add(f"| {c['title']} | {c['say']} | {c['verdict'].title() if c['verdict'] != 'info' else 'Info'} |")
        add("")

    zt = zone_table(conn, a)
    if zt:
        add("## Heart-rate zones")
        L.extend(zt)
        add("")

    splits = [s for s in r.get("splits", [])]
    if splits:
        full = [s for s in splits if s.get("complete") and s.get("pace_s_per_km")]
        add("## Pace and splits")
        if full:
            best = min(full, key=lambda s: s["pace_s_per_km"])
            h = len(full) // 2
            if h:
                first = sum(s["pace_s_per_km"] for s in full[:h]) / h
                second = sum(s["pace_s_per_km"] for s in full[-h:]) / h
                add(f"Best km: **{pace(best['pace_s_per_km'])}** (km {best['idx'] + 1})  ")
                add(f"First half: **{pace(first)}** · Second half: **{pace(second)}** ({second - first:+.0f} s/km)  ")
            add("")
        add("| Km | Pace | Flat-equivalent | HR | Zone | Cadence | Climb |")
        add("|---|---|---|---|---|---|---|")
        for s in splits:
            add(f"| {s['idx'] + 1}{'' if s.get('complete') else '*'} | {pace(s.get('pace_s_per_km'))} | {pace(s.get('gap_pace_s_per_km'))} | "
                f"{num(s.get('avg_hr'))} | {('Z' + str(s['zone'])) if s.get('zone') else '–'} | {num(s.get('cadence_spm'))} | "
                f"+{num(s.get('elevation_gain_m'), unit=' m')} |")
        add("")
        add("Flat-equivalent: the pace this effort would give on flat ground. * Partial km.")
        add("")

    efforts = [e for e in (r.get("best_efforts") or {}).values()]
    if efforts:
        add("## Best efforts in this run")
        add("| Distance | Time | Pace | Your best before |")
        add("|---|---|---|---|")
        for e in efforts:
            add(f"| {e['label']} | {clock(e['elapsed_s'])}{' (new best)' if e.get('is_best') else ''} | {pace(e.get('pace_s_per_km'))} | "
                f"{clock(e.get('previous_best_s'))} |")
        add("")

    dc = r.get("decoupling") or {}
    add("## Decoupling (heart-rate drift)")
    if dc.get("decoupling_pct") is not None:
        add(f"Pace:HR: **{dc['decoupling_pct']:.1f}%**" + (" (hill-adjusted pace)" if dc.get("grade_adjusted") else "") + "  ")
        if dc.get("power_decoupling_pct") is not None:
            add(f"Power:HR: **{dc['power_decoupling_pct']:.1f}%** ({dc.get('power_first_half_w')} W → {dc.get('power_second_half_w')} W)  ")
        else:
            add("Power:HR: no running power recorded  ")
        add("")
        add("First half against second half after a 10-minute warm-up; under 5% means the effort held steady." +
            ("" if dc.get("eligible") else " Indicative only: " + "; ".join(dc.get("reasons") or []) + "."))
    else:
        add("Not calculated: " + "; ".join(dc.get("reasons") or ["not enough heart-rate data"]) + ".")
    add("")

    comp = r.get("comparable") or {}
    if comp.get("runs"):
        add(f"## Similar runs ({comp['n']})")
        add(f"Criteria: {comp.get('criteria') or 'similar distance and climbing, steady'}.")
        add("")
        add("| Date | Distance | Pace | HR |")
        add("|---|---|---|---|")
        add(f"| **This run** | {num((a['distance_m'] or 0) / 1000, '{:.2f}', ' km')} | {pace(r.get('pace_moving_s_per_km'))} | {num(a.get('avg_hr'))} |")
        for c in comp["runs"]:
            add(f"| {c['local_date']} | {num((c.get('distance_m') or 0) / 1000, '{:.2f}', ' km')} | {pace(c.get('pace_s_per_km'))} | "
                f"{num(c.get('avg_hr'))} |")
        add("")

    if g:
        add("## From Garmin")
        for key, label, fmt in (("aerobicTrainingEffect", "Aerobic training effect", "{:.1f}"),
                                ("anaerobicTrainingEffect", "Anaerobic training effect", "{:.1f}"),
                                ("trainingEffectLabel", "Training effect", None), ("activityTrainingLoad", "Training load", "{:.0f}"),
                                ("calories", "Calories", "{:.0f}")):
            v = g.get(key)
            if v is not None:
                add(f"{label}: **{(fmt.format(v) if fmt and isinstance(v, (int, float)) else str(v).replace('_', ' ').title())}**  ")
        add("")

    wk = r.get("calendar_week") or {}
    if wk:
        add("## The week")
        add(f"{wk.get('start')} to {wk.get('end')}: **{wk.get('runs', 0)} runs**, "
            f"{num((wk.get('distance_m') or 0) / 1000, '{:.1f}', ' km')}, {clock(wk.get('moving_s'))} moving, "
            f"+{num(wk.get('elevation_gain_m'), unit=' m')} climb.")
        add("")

    if r.get("next_focus"):
        add("## Next focus")
        add(r["next_focus"])
        add("")

    mt = minute_table(conn, a)
    if mt:
        add("## Minute by minute")
        L.extend(mt)
        add("")

    add("## AI input")
    ok = one(conn.run_ai, {"source_id": sid, "status": "ok"}, sort=[("id", -1)])  # the newest AI input that passed its checks
    if ok:
        o = ok["output"]
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
        add(f"<small>Written by AI ({ok['model']}) on {ok['created_at'][:10]} from this run's analysis; numbers come from the app. "
            "Guidance, not medical advice.</small>")
    else:
        add("No AI input for this run yet.")
    add("")
    add(f"<small>Exported by Runner Sidekick{' ' + app_version if app_version else ''} on {datetime.now().strftime('%-d %B %Y')}.</small>")

    file_name = f"{start.strftime('%Y-%m-%d-%H%M%S')}-running.md"  # the same name the app gives the file
    return file_name, "\n".join(L) + "\n"
