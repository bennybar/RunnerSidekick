"""Training numbers, each with its history: lactate threshold (Garmin's), fitness, fatigue and form (the app's load
model), Garmin's race predictions over time, heart-rate recovery after hard efforts, and climbing speed (VAM).

Every item has the same shape: {id, title, status, value, headline, detail, basis, series: [{date, v}], lower_is_better},
so the app shows them all the same way. Garmin's numbers are labelled as Garmin's; the app's own say how they're made.

- Form: fitness (chronic load, fading over 28 days) minus fatigue (acute load, over 7 days), as a share of fitness. The
  loads are the readiness model's (heart-rate zones × minutes per run), so the bands are relative, not TrainingPeaks':
  above +20% fresh, −10 to +20% neutral, −30 to −10% productive training fatigue, below −30% heavy.
- Heart-rate recovery: the drop in heart rate over the 60 s after a hard effort (60+ s fast, ending in zone 4 or above,
  followed by a slower minute) in a run, the median over its efforts (2+). Measured while jogging, so smaller than a
  standing test; compare with yourself.
- Climbing speed (VAM): metres climbed per hour on the run's best sustained climb (3–10 minutes, 3%+ grade, 20+ m).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import exp
from statistics import median
from zoneinfo import ZoneInfo

from . import reports as rp
from .db import get_setting

NUMBERS_VERSION = "numbers-1.0"
FORM_BANDS = ((20, "Recent load well below your usual", "Your last week was much lighter than your usual training. That can mean "
                    "you're rested, or simply that you've trained less lately."),
              (-10, "Balanced", "Your last week was about in line with your usual training."),
              (-30, "Recent load above your usual", "Your last week was heavier than your usual training."),
              (None, "Recent load well above your usual", "Your last week was much heavier than your usual training; easier days "
                     "bring the balance back."))
QUIET_DAYS = 10  # this long without a run: the balance mostly says you've stopped, and it says that
RECOVERY_WINDOW_S, EFFORT_MIN_S = 60.0, 60.0
WALK_BELOW = 1.7  # m/s (about 10 min/km): slower recoveries count as walking or standing, faster as jogging
VAM_WINDOWS_S, VAM_MIN_GRADE, VAM_MIN_GAIN = (180, 300, 600), 0.03, 20.0
MAX_GAP_S = 10.0  # a climb can't span missing data longer than this
_vam_cache: dict = {}
_hrr_cache: dict = {}


def pace(speed_m_s: float) -> str:
    return rp.fmt_pace(1000 / speed_m_s) if speed_m_s else "—"


def hms(s: float) -> str:
    s = round(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%-d %b")


def change_since(series: list[dict], days: int, today: date) -> tuple[float, str] | None:
    """The latest value minus the one closest to `days` before it, with that date."""
    if len(series) < 2:
        return None
    target = (today - timedelta(days=days)).isoformat()
    then = min(series[:-1], key=lambda p: abs(date.fromisoformat(p["date"]).toordinal() - date.fromisoformat(target).toordinal()))
    return series[-1]["v"] - then["v"], then["date"]


# ---------------------------------------------------------------- lactate threshold (Garmin's)

def threshold(conn, today: date) -> dict:
    base = {"id": "threshold", "title": "Lactate threshold", "lower_is_better": True,
            "basis": "Garmin's estimate of the heart rate and pace you could hold for about an hour. It's what tempo and "
                     "threshold sessions are built around. Not calculated by the app."}
    th = get_setting(conn, "garmin_threshold", None) or {}
    pts = [p for p in th.get("points", []) if p.get("speed_m_s")]
    if not pts:
        return {**base, "status": "unavailable", "headline": "Not from Garmin yet",
                "detail": "Garmin estimates it from runs with heart rate, usually after a few harder efforts."}
    last = pts[-1]
    series = [{"date": p["date"], "v": round(1000 / p["speed_m_s"], 1), "label": pace(p["speed_m_s"])} for p in pts]
    ch = change_since(series, 56, today)
    trend = (f"{abs(ch[0]):.0f} s/km {'faster' if ch[0] < 0 else 'slower'} than on {day(ch[1])}" if ch and abs(ch[0]) >= 2
             else "about the same pace as two months ago" if ch else None)
    return {**base, "status": "ok", "value": f"{last['hr']:.0f} bpm · {pace(last['speed_m_s'])}" if last.get("hr") else pace(last["speed_m_s"]),
            "headline": trend or f"as of {day(last['date'])}", "detail": f"Garmin's latest, {day(last['date'])}.", "series": series}


# ---------------------------------------------------------------- fitness, fatigue and form

def form(conn, source: str, today: date) -> dict:
    from .readiness import ACUTE_DAYS, CHRONIC_DAYS, run_load
    base = {"id": "form", "title": "Training load balance", "lower_is_better": False, "neutral": True,
            "basis": "Your usual load (heart-rate zones × minutes, fading over 28 days) against your recent load (the same over 7 "
                     "days): (usual − recent) / usual. The bands (+20%, −10%, −30%) are the app's rules of thumb, not a published "
                     "scale. It describes how your recent training compares with your usual; it can't tell readiness to race, "
                     "and a high positive balance can just as well mean training less. The same load model as readiness."}
    tz = ZoneInfo(get_setting(conn, "timezone", "UTC"))
    zones = rp.hr_zones(conn)
    runs = rp.activities(conn, source, (today - timedelta(days=200)).isoformat(), today.isoformat())
    ends = []
    for a in runs:
        if a.get("start_utc") and (a.get("elapsed_s") or a.get("moving_s")):
            e = datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00")) + timedelta(seconds=a.get("elapsed_s") or a["moving_s"])
            ends.append((e, run_load(conn, a, zones["floors"] if zones else None)))
    if len(ends) < 6 or (today - ends[0][0].astimezone(tz).date()).days < 28:
        return {**base, "status": "not_enough", "headline": "Needs 4 weeks of runs", "detail": ""}
    first = ends[0][0]
    series = []
    for k in range(89, -1, -1):
        d = today - timedelta(days=k)
        end = datetime.combine(d + timedelta(days=1), time(0), tz).astimezone(timezone.utc)
        span = (end - first).total_seconds() / 86400 + 1
        if span < 28:
            continue
        done = [(e, l) for e, l in ends if e <= end]
        acute = sum(l * exp(-(end - e).total_seconds() / 86400 / ACUTE_DAYS) for e, l in done) / ACUTE_DAYS / (1 - exp(-span / ACUTE_DAYS))
        chronic = sum(l * exp(-(end - e).total_seconds() / 86400 / CHRONIC_DAYS) for e, l in done) / CHRONIC_DAYS / (1 - exp(-span / CHRONIC_DAYS))
        if chronic > 0:
            series.append({"date": d.isoformat(), "v": round(100 * (chronic - acute) / chronic), "fitness": round(chronic, 1),
                           "fatigue": round(acute, 1)})
    if not series:
        return {**base, "status": "not_enough", "headline": "Needs 4 weeks of runs", "detail": ""}
    now = series[-1]
    band = next(b for b in FORM_BANDS if b[0] is None or now["v"] >= b[0])
    for p in series:
        p["label"] = f"{p['v']:+d}%"
    quiet = (today - ends[-1][0].astimezone(tz).date()).days
    headline, detail = band[1], band[2]
    if quiet >= QUIET_DAYS:
        headline, detail = "Little recent training", f"No run in {quiet} days: the balance mostly reflects the break."
    return {**base, "status": "ok", "value": f"{now['v']:+d}%", "headline": headline, "detail":
            f"{detail} Usual load {now['fitness']:.0f}, recent {now['fatigue']:.0f} (per day).", "series": series}


# ---------------------------------------------------------------- race predictions over time (Garmin's)

def predictions(conn, today: date) -> dict:
    base = {"id": "predictions", "title": "Race predictions over time", "lower_is_better": True,
            "basis": "Garmin's predicted race times, day by day. Garmin's estimate from your VO₂ max and training, not a result."}
    rows = [r for r in get_setting(conn, "garmin_predictions", None) or [] if r.get("5k")]
    if len(rows) < 2:
        return {**base, "status": "unavailable", "headline": "Not from Garmin yet", "detail": ""}
    series = [{"date": r["date"], "v": r["5k"], "label": hms(r["5k"])} for r in rows]
    last = rows[-1]
    ch = change_since(series, 56, today)
    trend = (f"5K {abs(ch[0]):.0f} s {'faster' if ch[0] < 0 else 'slower'} than on {day(ch[1])}" if ch and abs(ch[0]) >= 5
             else "about the same as two months ago" if ch else "")
    others = ", ".join(f"{lab} {hms(last[k])}" for k, lab in (("10k", "10K"), ("half", "half"), ("marathon", "marathon")) if last.get(k))
    return {**base, "status": "ok", "value": f"5K {hms(last['5k'])}", "headline": trend, "detail": f"Now: {others}.", "series": series}


# ---------------------------------------------------------------- heart-rate recovery

def recovery_drops(s, floor4: float) -> list[dict]:
    """Each hard effort's heart-rate drop over the following 60 s (bpm, kept whatever it is) and the recovery's speed.
    Only the recording's quality decides what counts: continuous heart rate through the minute, a real effort."""
    pts = [(t, h, v) for t, h, v in zip(s.t, s.hr, s.speed) if t is not None and h is not None and v is not None]
    if len(pts) < 30:
        return []
    moving = sorted(v for _, _, v in pts if v > 0.5)
    if not moving:
        return []
    fast = moving[len(moving) // 4] * 1.25  # well above the run's easier running (its slower quarter): efforts can be half a session

    def avg(t0, t1, k):  # mean of field k over [t0, t1]
        xs = [p[k] for p in pts if t0 <= p[0] <= t1]
        return sum(xs) / len(xs) if xs else None
    drops, i, n = [], 0, len(pts)
    while i < n:
        if pts[i][2] < fast:
            i += 1
            continue
        j = i
        while j + 1 < n and pts[j + 1][2] >= fast * 0.9 and pts[j + 1][0] - pts[j][0] <= 5:
            j += 1
        start, end = pts[i][0], pts[j][0]
        if end - start >= EFFORT_MIN_S:
            peak = avg(end - 5, end, 1)
            later = avg(end + RECOVERY_WINDOW_S - 3, end + RECOVERY_WINDOW_S + 3, 1)
            slow = avg(end + 5, end + RECOVERY_WINDOW_S, 2)
            gap_free = all(b[0] - a[0] <= 5 for a, b in zip(pts, pts[1:]) if end <= a[0] <= end + RECOVERY_WINDOW_S)
            covered = pts[-1][0] >= end + RECOVERY_WINDOW_S  # the recording runs the whole minute
            if peak and later and slow is not None and peak >= floor4 and slow <= 0.8 * avg(start, end, 2) and gap_free and covered:
                drops.append({"drop": round(peak - later, 1), "recovery_speed": round(slow, 2)})
        i = j + 1
    return drops


def recovery(conn, source: str, today: date) -> dict:
    base = {"id": "recovery", "title": "Heart-rate recovery", "lower_is_better": False,
            "basis": "How far heart rate falls in the minute after a hard effort (60+ s fast, ending in zone 4 or above), median "
                     "per session. Every effort with continuous heart rate counts, whatever the result. How you recover changes "
                     "it as much as fitness does (walking drops more than jogging), so sessions are compared only with ones "
                     "recovered the same way. Measured on the move, smaller than a standing test. Experimental."}
    zones = rp.hr_zones(conn)
    if not zones:
        return {**base, "status": "unavailable", "headline": "Needs heart-rate zones", "detail": ""}
    series = []
    for a in rp.activities(conn, source, (today - timedelta(days=180)).isoformat(), today.isoformat()):
        key = (rp.run_key(conn, a), zones["floors"][3])
        if key not in _hrr_cache:
            s = rp.samples_for(conn, a["id"])
            _hrr_cache[key] = recovery_drops(s, zones["floors"][3]) if s else []
        drops = _hrr_cache[key]
        if len(drops) >= 2:
            v = median(d["drop"] for d in drops)
            how = "walking" if median(d["recovery_speed"] for d in drops) < WALK_BELOW else "jogging"
            series.append({"date": a["local_date"], "v": round(v), "label": f"{round(v)} bpm · {how} recoveries", "how": how,
                           "source_id": a["source_id"], "efforts": len(drops)})
    if not series:
        return {**base, "status": "not_enough", "headline": "Needs a session with hard efforts and easier recoveries",
                "detail": "Intervals or repeats with slower jogs or walks between them, in the last 6 months."}
    last = series[-1]
    alike = [p for p in series if p["how"] == last["how"]]
    prev = alike[-2] if len(alike) >= 2 else None
    trend = (f"{abs(last['v'] - prev['v'])} bpm {'more' if last['v'] > prev['v'] else 'less'} than on {day(prev['date'])} "
             f"(also {last['how']})" if prev and last["v"] != prev["v"] else f"the same as on {day(prev['date'])}" if prev
             else f"the first session with {last['how']} recoveries")
    return {**base, "status": "ok", "value": f"−{last['v']} bpm in a minute", "headline": trend,
            "detail": f"Median of {last['efforts']} efforts on {day(last['date'])}, {last['how']} between them.",
            "series": alike}


# ---------------------------------------------------------------- climbing speed (VAM)

def best_climb(s) -> dict | None:
    """The run's fastest sustained climb: metres gained per hour over 3–10 minutes at 3%+ grade, 20+ m."""
    pts = [(t, d, e) for t, d, e in zip(s.t, s.dist, s.elev) if t is not None and d is not None and e is not None]
    if len(pts) < 20:
        return None
    grid, k = [], 0  # resampled to 10 s; a point inside a gap in the recording is None, never interpolated across
    t = pts[0][0]
    while t <= pts[-1][0]:
        while k + 1 < len(pts) and pts[k + 1][0] < t:
            k += 1
        a, b = pts[k], pts[min(k + 1, len(pts) - 1)]
        if b[0] - a[0] > MAX_GAP_S:
            grid.append(None)
        else:
            f = 0 if b[0] == a[0] else (t - a[0]) / (b[0] - a[0])
            grid.append((t, a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2])))
        t += 10
    best = None
    for w in VAM_WINDOWS_S:
        n = w // 10
        bad = [0]  # running count of gap points, so a window with any is skipped
        for g in grid:
            bad.append(bad[-1] + (g is None))
        for i in range(n, len(grid)):
            if bad[i + 1] - bad[i - n] > 0:
                continue
            (t0, d0, e0), (t1, d1, e1) = grid[i - n], grid[i]
            gain, dist = e1 - e0, d1 - d0
            if gain >= VAM_MIN_GAIN and dist > 0 and gain / dist >= VAM_MIN_GRADE:
                vam = gain / (t1 - t0) * 3600
                # The fastest; at about the same speed, the longer climb (it's the more sustained one)
                if best is None or vam > best["vam"] + 10 or (vam > best["vam"] - 10 and gain > best["gain_m"]):
                    best = {"vam": round(vam), "gain_m": round(gain), "minutes": round((t1 - t0) / 60), "grade": round(100 * gain / dist, 1)}
    return best


def climb_of(conn, a: dict) -> dict | None:
    key = rp.run_key(conn, a)
    if key not in _vam_cache:
        s = rp.samples_for(conn, a["id"])
        _vam_cache[key] = best_climb(s) if s else None
    return _vam_cache[key]


def climbing(conn, source: str, today: date) -> dict:
    base = {"id": "climbing", "title": "Climbing speed (VAM)", "lower_is_better": False,
            "basis": "Metres climbed per hour on each run's best sustained climb (3–10 minutes, at least 3% and 20 m). "
                     "Higher means stronger uphill; it depends on the hill, so compare similar climbs."}
    series = []
    for a in rp.activities(conn, source, (today - timedelta(days=365)).isoformat(), today.isoformat()):
        c = climb_of(conn, a)
        if c:
            series.append({"date": a["local_date"], "v": c["vam"], "label": f"{c['vam']} m/h", "source_id": a["source_id"], **c})
    if not series:
        return {**base, "status": "not_enough", "headline": "No sustained climbs yet", "detail": "Needs a run with a climb of 3 minutes or more."}
    recent = [p for p in series if p["date"] >= (today - timedelta(days=90)).isoformat()]
    when = "best in 90 days" if recent else "best in the last year (none in 90 days)"
    top = max(recent or series, key=lambda p: p["v"])
    for p in series:
        p["label"] = f"{p['v']} m/h · {p['minutes']} min at {p['grade']}%"  # the climb's length and grade: compare like with like
    return {**base, "status": "ok", "value": f"{top['v']} m/h", "headline": f"{when}: +{top['gain_m']} m in {top['minutes']} min at {top['grade']}%",
            "detail": f"On {day(top['date'])}.", "series": series, "source_id": top["source_id"]}


def build(conn, source: str, today: date) -> dict:
    return {"items": [threshold(conn, today), form(conn, source, today), predictions(conn, today), recovery(conn, source, today),
                      climbing(conn, source, today)], "algorithm_version": NUMBERS_VERSION}
