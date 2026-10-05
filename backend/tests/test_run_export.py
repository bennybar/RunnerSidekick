from datetime import date, datetime, timedelta, timezone

from sidekick import reports as rp
from sidekick import run_export, weather
from sidekick.connectors.base import Samples
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, next_id, user_db_name, utc_now
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def synced():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    return conn, rp.activities(conn, "fixture", "2026-09-01", ANCHOR.isoformat())[-1]["source_id"]


def no_net(*a, **k):
    raise AssertionError("no network in tests")


def test_export_v2_sections_in_order_and_the_layers_kept_apart():
    conn, sid = synced()
    name, md = run_export.markdown(conn, "fixture", sid, app_version="0.30.0", fetch=no_net)
    assert name.endswith("-running.md") and md.startswith("# Running")
    order = ["## How it went", "## Pace and splits", "## Aerobic decoupling (heart-rate drift)", "## AI input",
             "## App-generated interpretation", "## Minute by minute", "## Data provenance"]
    assert [md.index(s) for s in order] == sorted(md.index(s) for s in order)
    assert "## Athlete context" not in md  # nothing entered: no section, no placeholders
    assert "Data-based classification:" in md and "Not stated by the runner." in md
    assert "<details>" in md and "Export schema: **Runner Sidekick LLM Export v2**" in md and "App version: **0.30.0**" in md
    assert "| Metric | First half | Second half | Change |" in md and "Warm-up excluded: **first 10 min" in md
    assert "No AI interpretation for this run yet." in md
    conn.run_ai.insert_one({"id": next_id(conn, "run_ai"), "source_id": sid, "input_hash": "x", "model": "m", "status": "ok",
                            "output": {"tldr": "Solid run.", "summary": "Even effort.", "went_well": [{"text": "Pacing"}],
                                       "to_work_on": [], "next_time": {"text": "Keep it easy.", "direction": "easier"}},
                            "created_at": utc_now()})
    _, md = run_export.markdown(conn, "fixture", sid, fetch=no_net)
    interp = md[md.index("## App-generated interpretation"):md.index("## Minute by minute")]
    assert "**TL;DR:** Solid run." in interp and "Interpretation, not source data" in interp
    assert "Solid run" not in md[:md.index("## App-generated interpretation")]  # never mixed into the facts
    assert run_export.markdown(conn, "fixture", "nope", fetch=no_net) is None


def test_stated_intent_and_context_override_the_inferred_type():
    conn, sid = synced()
    a = rp.activity_by_source_id(conn, "fixture", sid)
    conn.run_intent.insert_one({"activity_source_id": sid, "kind": "steady", "note": "Feet tired after standing all day.",
                                "source": "user", "client_updated_at": utc_now(), "target": "HR <= 160 bpm",
                                "feel": "good", "limiter": "feet", "health": "recovering"})
    r = rp.build_post_run(conn, "fixture", sid, False)
    assert r["intent"]["kind"] == "steady" and r["intent"]["feel"] == "good"
    assert r["classified"]["source"] == "inferred"  # kept beside it, not in its place
    hr = a["avg_hr"]
    assert ("cap worked" in r["next_focus"]) == (hr <= 162)
    _, md = run_export.markdown(conn, "fixture", sid, fetch=no_net)
    ctx = md[md.index("## Athlete context"):md.index("## How it went")]
    assert "Intent: **Steady aerobic**" in ctx and "Target: **HR <= 160 bpm**" in ctx and "Primary limiter: **Feet**" in ctx
    assert "Health status: **Recovering from illness**" in ctx and "Feet tired" in ctx
    assert "User intent: **Steady aerobic**" in md and "the runner's intent comes first" in md
    assert "reported limiter (feet)" in md


def test_hr_cap_from_target_text():
    assert rp.hr_cap("HR <= 160 bpm") == 160 and rp.hr_cap("stay below 150") == 150 and rp.hr_cap("155 bpm") == 155
    assert rp.hr_cap("5:30–5:40 /km") is None and rp.hr_cap(None) is None


class Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_weather_sends_only_rounded_position_and_is_kept():
    conn, sid = synced()
    a = rp.activity_by_source_id(conn, "fixture", sid)
    assert weather.for_run(conn, a, no_net) is None  # no GPS position stored: no lookup at all
    conn.raw_payload.insert_one({"source": "fixture", "kind": "activity_summary", "source_key": sid,
                                 "payload": {"startLatitude": 31.785141, "startLongitude": 34.762619}})
    start = datetime.fromisoformat(a["start_utc"].replace("Z", "+00:00"))
    hour = (start + timedelta(seconds=a["elapsed_s"] / 2 + 1800)).replace(minute=0, second=0, microsecond=0)
    seen = {}

    def fake(url, params, timeout):
        seen.update(params)
        return Resp({"hourly": {"time": [hour.strftime("%Y-%m-%dT%H:00")], "temperature_2m": [25.2], "relative_humidity_2m": [70],
                                "dew_point_2m": [19.1], "apparent_temperature": [26.4], "wind_speed_10m": [8.0]}})
    w = weather.for_run(conn, a, fake)
    assert seen["latitude"] == 31.79 and seen["longitude"] == 34.76 and w["temperature_2m"] == 25.2
    assert weather.for_run(conn, a, no_net) == w  # kept with the run
    _, md = run_export.markdown(conn, "fixture", sid, fetch=no_net)
    assert "## Conditions" in md and "Temperature: **25°C**" in md and "not recorded by the watch" in md
    assert "Weather: **Open-Meteo" in md


def test_halves_and_dynamics_round_trip():
    t = [float(i) for i in range(0, 1200, 2)]
    s = Samples(t, [150.0] * len(t), [3.0] * len(t), [3.0 * x for x in t], [10.0] * len(t), [170.0] * len(t),
                [300.0] * len(t), {"gct": [260.0 if x < 600 else 270.0 for x in t], "bb": [60.0] * len(t)})
    assert Samples.from_json(s.to_json()).dyn == s.dyn
    h = run_export.halves(s, s.dyn["gct"])
    assert round(h[0]) == 260 and round(h[1]) == 270
    assert run_export.halves(s, [None] * len(t)) is None
