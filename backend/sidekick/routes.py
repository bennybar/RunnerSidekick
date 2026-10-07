"""Repeat routes: recognising the runs you do over and over, from simplified route geometry, and how they've gone.

What's stored: for each outdoor run, a simplified route, one point every 50 m along the run, rounded to 4 decimal places
(about 11 m), in `route_shape`. Kept as long as the run is, deleted with it (Delete everything, or the account). The full
GPS track isn't kept: it's removed from the stored raw Garmin data as soon as the simplified route exists (Garmin still
has it). Routes are never sent to the AI.

Identification (geometry only):
- Shortlist: similar distance (±12%) and overlapping areas. Start, end, distance and climb never decide a match.
- Match: each route covers the other (95% of the points of each within 40 m of the other's line: a small detour fits,
  a different route doesn't), in the same direction (positions along the other route advance in step; a loop started
  at another point still matches, an opposite-direction run doesn't). Only these high-confidence matches group runs;
  near misses (coverage 80–95%) are left apart.
- Corrections: "Different route" takes a run out of a route for good.

How each route has gone is a separate step (`progress`): same-route runs of the same kind (easy and steady apart from
hard), cool runs only, compared at similar average heart rate. Conditions are shown, not mixed into identification.
"""

from __future__ import annotations

import math
from datetime import date
from statistics import median

SPACING_M = 50.0
NEAR_M = 40.0
COVER_HIGH, COVER_POSSIBLE = 0.95, 0.80
SAME_DIRECTION = 0.85     # share of steps that advance along the other route
LOOP_CLOSE_M = 200.0      # a route whose start and end are this close is a loop
DIST_TOLERANCE = 0.12
ROUTES_VERSION = "routes-1.0"


# ---------------------------------------------------------------- geometry

def shape_from_track(dist: list, lat: list, lon: list) -> list[list[float]] | None:
    """Points every 50 m along the distance, from the GPS track, rounded to ~11 m. None without a usable track."""
    pts = [(d, la, lo) for d, la, lo in zip(dist, lat, lon)
           if d is not None and la is not None and lo is not None and -90 <= la <= 90 and -180 <= lo <= 180 and (la, lo) != (0, 0)]
    if len(pts) < 10 or pts[-1][0] - pts[0][0] < 500:
        return None
    out, k = [], 0
    target = pts[0][0]
    while target <= pts[-1][0]:
        while k + 1 < len(pts) and pts[k + 1][0] < target:
            k += 1
        a, b = pts[k], pts[min(k + 1, len(pts) - 1)]
        f = 0 if b[0] == a[0] else (target - a[0]) / (b[0] - a[0])
        out.append([round(a[1] + f * (b[1] - a[1]), 4), round(a[2] + f * (b[2] - a[2]), 4)])
        target += SPACING_M
    return out


def _xy(pts, lat0, lon0):
    k = math.cos(math.radians(lat0))
    return [((lo - lon0) * 111_320 * k, (la - lat0) * 110_540) for la, lo in pts]


def _project(p, line, cum):
    """Distance from point p to polyline `line`, and how far along it the nearest point is (metres)."""
    best = (float("inf"), 0.0)
    for i in range(len(line) - 1):
        (x1, y1), (x2, y2) = line[i], line[i + 1]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - x1) * dx + (p[1] - y1) * dy) / L2))
        qx, qy = x1 + t * dx, y1 + t * dy
        d = math.hypot(p[0] - qx, p[1] - qy)
        if d < best[0]:
            best = (d, cum[i] + t * math.sqrt(L2))
    return best


FOLLOW_SHARE = 0.9
FOLLOW_AHEAD = 30   # points (about 1.5 km) ahead to look for the next match: room for a detour
FOLLOW_NEAR_M = 60.0  # point to point (50 m spacing), so a little looser than point to line


def follows(A: list, B: list, loop: bool) -> float:
    """The share of A's points matched while moving forward along B, starting where A starts."""
    n = len(B)
    j = min(range(n), key=lambda k: math.hypot(A[0][0] - B[k][0], A[0][1] - B[k][1]))
    ok = 0
    for p in A:
        best = None
        for step in range(0, FOLLOW_AHEAD):  # forward or staying, never back (reversed runs must not crawl along)
            k = j + step
            if loop:
                k %= n
            elif not 0 <= k < n:
                continue
            d = math.hypot(p[0] - B[k][0], p[1] - B[k][1])
            if best is None or d < best[0]:
                best = (d, k)
        if best and best[0] <= FOLLOW_NEAR_M:
            ok += 1
            j = best[1]
    return ok / len(A)


def _cum(line):
    out = [0.0]
    for a, b in zip(line, line[1:]):
        out.append(out[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return out


def compare(a: list, b: list) -> dict:
    """How two simplified routes relate: coverage each way, direction, loop, and the confidence of a match."""
    lat0, lon0 = a[0]
    A, B = _xy(a, lat0, lon0), _xy(b, lat0, lon0)
    ca, cb = _cum(A), _cum(B)
    near_a = [_project(p, B, cb) for p in A]
    near_b = [_project(p, A, ca) for p in B]
    cov_ab = sum(1 for d, _ in near_a if d <= NEAR_M) / len(A)
    cov_ba = sum(1 for d, _ in near_b if d <= NEAR_M) / len(B)
    loop = math.hypot(B[0][0] - B[-1][0], B[0][1] - B[-1][1]) <= LOOP_CLOSE_M
    # Direction: walk along A and follow B forward from where we are (wrapping round a loop). An out-and-back's two legs
    # overlap, so "nearest point anywhere" can't tell them apart; following can. Reversed, B is only followed backwards.
    if follows(A, B, loop) >= FOLLOW_SHARE:
        direction = "same"
    elif follows(A, B[::-1], loop) >= FOLLOW_SHARE:
        direction = "opposite"
    else:
        direction = "unclear"
    cover = min(cov_ab, cov_ba)
    confidence = ("high" if cover >= COVER_HIGH and direction == "same" else
                  "possible" if cover >= COVER_POSSIBLE else "no")
    return {"coverage": round(cover, 3), "direction": direction, "loop": loop, "confidence": confidence}


def is_loop(pts) -> bool:
    (x1, y1), (x2, y2) = _xy([pts[0], pts[-1]], *pts[0])
    return math.hypot(x2 - x1, y2 - y1) <= LOOP_CLOSE_M


def strip_gps(details: dict) -> dict:
    """Garmin's activity details without the GPS track (the latitude and longitude columns and the map polyline), for
    keeping as raw data once the simplified route exists."""
    idx = {m.get("key"): m.get("metricsIndex") for m in details.get("metricDescriptors") or []}
    gone = [i for k, i in idx.items() if k in ("directLatitude", "directLongitude") and i is not None]
    out = {k: v for k, v in details.items() if k != "geoPolylineDTO"}
    rows = []
    for r in details.get("activityDetailMetrics") or []:
        m = list(r.get("metrics") or [])
        for i in gone:
            if i < len(m):
                m[i] = None
        rows.append({**r, "metrics": m})
    out["activityDetailMetrics"] = rows
    return out


def shape_from_details(details: dict | None) -> list | None:
    if not details:
        return None
    idx = {m.get("key"): m.get("metricsIndex") for m in details.get("metricDescriptors") or []}
    if any(idx.get(k) is None for k in ("sumDistance", "directLatitude", "directLongitude")):
        return None
    rows = [r.get("metrics") or [] for r in details.get("activityDetailMetrics") or []]

    def col(k):
        i = idx[k]
        return [r[i] if i < len(r) and isinstance(r[i], (int, float)) else None for r in rows]
    return shape_from_track(col("sumDistance"), col("directLatitude"), col("directLongitude"))


def _bbox(pts):
    las, los = [p[0] for p in pts], [p[1] for p in pts]
    return min(las), max(las), min(los), max(los)


def _overlap(b1, b2, pad=0.001):
    return not (b1[1] + pad < b2[0] or b2[1] + pad < b1[0] or b1[3] + pad < b2[2] or b2[3] + pad < b1[2])


# ---------------------------------------------------------------- grouping

def groups(conn, source: str) -> dict:
    """{route_id: [source_id, ...]} for routes run 2+ times, oldest run first; the route's id is its first run's.
    Deterministic, so the same runs always group the same way; corrections are respected."""
    from . import reports as rp
    shapes = {r["source_id"]: r["points"] for r in conn.route_shape.find({}, {"source_id": 1, "points": 1})}
    runs = [a for a in rp.activities(conn, source, "0000-01-01", "9999-12-31") if a["source_id"] in shapes]
    apart = {}
    for o in conn.route_override.find({}):
        apart.setdefault(o["source_id"], set()).add(o["not_route"])
    reps: list[dict] = []
    for a in runs:
        sid, pts = a["source_id"], shapes[a["source_id"]]
        box, dist = _bbox(pts), a.get("distance_m") or len(pts) * SPACING_M
        home = None
        for g in reps:
            if g["id"] in apart.get(sid, ()) or abs(dist - g["dist"]) > DIST_TOLERANCE * g["dist"] or not _overlap(box, g["box"]):
                continue  # the shortlist: distance and area only narrow it down
            if compare(pts, g["pts"])["confidence"] == "high":
                home = g
                break
        if home:
            home["members"].append(sid)
        else:
            reps.append({"id": sid, "pts": pts, "box": box, "dist": dist, "members": [sid]})
    return {g["id"]: g["members"] for g in reps if len(g["members"]) >= 2}


def route_of(conn, source: str, sid: str) -> tuple[str, list[str]] | None:
    for rid, members in groups(conn, source).items():
        if sid in members:
            return rid, members
    return None


def different_route(conn, source: str, sid: str) -> bool:
    """The runner says this run isn't that route: it stays out of it from now on."""
    found = route_of(conn, source, sid)
    if not found:
        return False
    conn.route_override.update_one({"source_id": sid, "not_route": found[0]}, {"$set": {"source_id": sid, "not_route": found[0]}}, upsert=True)
    return True


# ---------------------------------------------------------------- how a route has gone (separate from identifying it)

EASY = {"easy", "long", "recovery", "steady", "progression"}
HR_MATCH_BPM = 5


def run_row(conn, source: str, a: dict) -> dict:
    from . import reports as rp
    from . import weather as wx
    rep = conn.report.find_one({"type": "post_run", "subject_key": a["source_id"]}, sort=[("revision", -1)])
    kind = ((rep or {}).get("body") or {}).get("intent", {}).get("kind") or "easy"
    ht = wx.heat(wx.stored(conn, a["source_id"]))
    return {"source_id": a["source_id"], "date": a["local_date"], "distance_m": a["distance_m"],
            "pace_s_per_km": rp.rn.moving_pace(a["distance_m"], a["moving_s"]), "avg_hr": a.get("avg_hr"),
            "kind": "easy" if kind in EASY else "hard", "temperature_c": (ht or {}).get("temperature_c"), "hot": bool(ht and ht["hot"])}


def progress(rows: list[dict]) -> str | None:
    """At similar heart rate, how the route's pace moved: the first runs against the latest, same kind, cool runs only."""
    for kind in ("easy", "hard"):
        rs = [r for r in rows if r["kind"] == kind and not r["hot"] and r["avg_hr"] and r["pace_s_per_km"]]
        if len(rs) < 4:
            continue
        early, late = rs[:2], rs[-2:]
        h1, h2 = median(r["avg_hr"] for r in early), median(r["avg_hr"] for r in late)
        if abs(h1 - h2) > HR_MATCH_BPM:
            continue
        from . import reports as rp
        p1, p2 = median(r["pace_s_per_km"] for r in early), median(r["pace_s_per_km"] for r in late)
        word = "faster" if p2 < p1 else "slower"
        months = (date.fromisoformat(early[0]["date"]).strftime("%b"), date.fromisoformat(late[-1]["date"]).strftime("%b"))
        return (f"{'Easy' if kind == 'easy' else 'Hard'} runs at about {round((h1 + h2) / 2)} bpm: {rp.fmt_pace(p1)} → "
                f"{rp.fmt_pace(p2)} ({months[0]} → {months[1]}), {abs(round(p1 - p2))} s/km {word} at a similar heart rate")
    return None


def summary(conn, source: str, rid: str, members: list[str], number: int) -> dict:
    from . import reports as rp
    rows = [run_row(conn, source, a) for a in (rp.activity_by_source_id(conn, source, s) for s in members) if a]
    first = rows[0]
    loop = is_loop(conn.route_shape.find_one({"source_id": rid})["points"])
    return {"id": rid, "name": f"Route {number}", "distance_km": round(median(r["distance_m"] for r in rows) / 1000, 1),
            "loop": loop, "runs": len(rows), "first": first["date"], "last": rows[-1]["date"], "progress": progress(rows),
            "rows": rows}


def all_routes(conn, source: str) -> list[dict]:
    gs = groups(conn, source)
    return [summary(conn, source, rid, members, i + 1) for i, (rid, members) in enumerate(gs.items())]


BASIS = ("Recognised from each run's simplified route (a point every 50 m, rounded to about 11 m): two runs are the same route "
         "when each covers the other and they go the same way, small detours allowed; a loop started elsewhere still counts, "
         "the opposite direction doesn't. Only confident matches are grouped. Progress compares runs of the same kind, cool "
         "ones only, at a similar heart rate. Kept as long as the run; the full GPS track isn't stored.")
