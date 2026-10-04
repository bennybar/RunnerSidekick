import time
from datetime import date

from fastapi.testclient import TestClient

from helpers import set_plan
from sidekick import focus as fc
from sidekick import reports as rp
from sidekick.api import create_app
from sidekick.auth import create_token
from sidekick.config import Config
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, set_setting, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)  # Wednesday; fixture runs Mon, Wed, Fri, Sat


def synced(tmp_path):
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 60, 3, max_backfill_days=90)
    rp.build_insights(conn, "fixture", ANCHOR, True)
    return conn


def set_zones(conn):
    set_setting(conn, "source_hr_zones", {"floors": [95, 113, 132, 151, 170], "method": "HR_MAX", "max_hr": 189})


def test_suggestion_speaks_to_the_planned_session():
    hard = {"state": "consider_easier", "suppress_intensity": True, "planned_run_day": True}
    assert "swapping the interval session" in rp.suggestion_text(hard, {"kind": "intervals", "minutes": 50}, 132)
    ok = {"state": "usual_plan", "suppress_intensity": False, "planned_run_day": True}
    s = rp.suggestion_text(ok, {"kind": "easy", "minutes": 40}, 132)
    assert "easy run of about 40 min" in s and "below 132 bpm" in s
    unsure = {"state": "insufficient_data", "suppress_intensity": True, "planned_run_day": True}
    assert "optional" in rp.suggestion_text(unsure, {"kind": "tempo"}, 132)
    assert rp.suggestion_text(ok, {"kind": "rest"}, 132).startswith("Rest day planned")


def test_planned_easy_run_that_was_hard_is_flagged(tmp_path):
    conn = synced(tmp_path)
    set_zones(conn)
    sid = "fx-run-2026-09-28"
    set_plan(conn, "2026-09-28", "easy", 40)
    r = rp.build_post_run(conn, "fixture", sid, True)
    assert r["intent"] == {"kind": "easy", "note": None, "source": "plan"}  # pre-filled from the plan
    flagged = [f for f in r["findings"] if f["metric"] == "intent_vs_actual"]
    assert flagged and "planned this as an easy run" in flagged[0]["statement"]  # fixture HR sits well above 132
    assert "meant to be easy" in r["next_focus"]


def test_focus_options_follow_data_and_goal(tmp_path):
    conn = synced(tmp_path)
    set_zones(conn)
    rp.build_insights(conn, "fixture", ANCHOR, True)
    kinds = [o["kind"] for o in fc.options(conn, "fixture", ANCHOR)]
    assert "consistency" in kinds or "easy_runs" in kinds
    set_setting(conn, "goal_type", "consistency")
    assert fc.options(conn, "fixture", ANCHOR)[0]["kind"] == "consistency"


def test_focus_evaluation_partial_week_is_in_progress_then_final(tmp_path):
    conn = synced(tmp_path)
    ws = fc.week_start(ANCHOR)  # Mon 28 Sep; runs on Mon and Wed so far
    fc.choose(conn, ws, "consistency")
    mid = fc.evaluate(conn, "fixture", ws, "consistency", ANCHOR)
    assert mid["status"] == "in_progress" and "of 2 planned days so far" in mid["summary"]
    last = fc.week_start(date(2026, 9, 21))
    done = fc.evaluate(conn, "fixture", last, "consistency", ANCHOR)
    assert done["complete"] and done["status"] == "achieved"  # fixture ran Mon/Wed/Fri/Sat = the default running days


def test_even_pacing_focus_measures_fade(tmp_path):
    conn = synced(tmp_path)
    e = fc.evaluate(conn, "fixture", date(2026, 9, 21), "even_pacing", ANCHOR)
    assert e["runs"] and all("value" in r for r in e["runs"]) and e["baseline"]["n"] > 0


def test_insight_novelty_and_dismissal_lapse(tmp_path):
    conn = synced(tmp_path)
    first = {i["id"]: i for i in rp.build_insights(conn, "fixture", ANCHOR, True)["insights"]}
    assert all(i["novelty"] == "new" for i in first.values())
    nxt = {i["id"]: i for i in rp.build_insights(conn, "fixture", date(2026, 10, 1), True)["insights"]}
    assert any(i["novelty"] == "continuing" for i in nxt.values())
    pid = next(k for k, i in nxt.items() if i["verdict"] == "pattern")
    conn.insight_state.insert_one({"insight_id": pid, "state": "dismissed", "verdict_at_dismissal": nxt[pid]["verdict"], "updated_at": "x"})
    again = {i["id"]: i for i in rp.build_insights(conn, "fixture", date(2026, 10, 1), True)["insights"]}
    assert again[pid]["user_state"] == "dismissed"
    conn.insight_state.update_one({"insight_id": pid}, {"$set": {"verdict_at_dismissal": "no_clear_pattern"}})
    assert {i["id"]: i for i in rp.build_insights(conn, "fixture", date(2026, 10, 1), True)["insights"]}[pid]["user_state"] is None


def test_loop_endpoints(tmp_path):
    c = Config(data_dir=tmp_path, source="fixture", timezone="Asia/Jerusalem", backfill_days=40, refetch_days=3,
               raw_retention_days=120, request_spacing_s=0)
    h = {"Authorization": f"Bearer {create_token(tmp_path, 't')}"}
    client = TestClient(create_app(c, connector=FixtureConnector(ANCHOR)))
    client.post("/v1/sync", headers=h)
    for _ in range(100):
        if not client.get("/v1/status", headers=h).json()["sync_running"]:
            break
        time.sleep(0.05)
    r = client.put("/v1/plan/2026-09-30", json={"kind": "intervals", "minutes": 45, "client_updated_at": "2026-09-30T05:00:00Z"}, headers=h)
    assert r.status_code == 200 and r.json()["recommendation"]["plan"]["kind"] == "intervals"
    stale = client.put("/v1/plan/2026-09-30", json={"kind": "rest", "client_updated_at": "2026-09-30T04:00:00Z"}, headers=h)
    assert stale.json()["recommendation"]["plan"]["kind"] == "intervals"  # last writer wins
    acts = client.get("/v1/activities", headers=h).json()
    ir = client.put(f"/v1/activities/{acts[0]['source_id']}/intent", json={"kind": "tempo", "note": "felt strong", "client_updated_at": "z"}, headers=h)
    assert ir.json()["intent"]["kind"] == "tempo" and ir.json()["intent"]["source"] == "user"
    ir = client.put(f"/v1/activities/{acts[0]['source_id']}/intent", headers=h, json={
        "kind": "steady", "target": " HR <= 160 ", "feel": "good", "limiter": "feet", "health": None, "note": "", "client_updated_at": "zz"})
    it = ir.json()["intent"]
    assert it["kind"] == "steady" and it["target"] == "HR <= 160" and it["limiter"] == "feet" and "health" not in it and not it["note"]
    assert client.put(f"/v1/activities/{acts[0]['source_id']}/intent", headers=h,
                      json={"kind": "steady", "feel": "meh", "client_updated_at": "zzz"}).status_code == 422
    f = client.put("/v1/focus", json={"kind": "easy_runs"}, headers=h).json()
    assert f["current"]["kind"] == "easy_runs" and f["options"]
    assert client.put("/v1/focus", json={"kind": "nonsense"}, headers=h).status_code == 422


def test_load_signal_without_baselines_is_cautious_not_typical():
    from sidekick.analytics.recommend import recommend
    r = recommend({"load": ["m:load7"]}, {"energy": 5, "pain": False, "illness": False}, has_overnight_data=True, any_baseline=False)
    r["planned_run_day"] = True
    assert r["rule_id"] == "R1e" and r["suppress_intensity"]
    assert "typical" not in rp.headline(r, [], {}).lower()
    assert "optional" in rp.suggestion_text(r, {"kind": "intervals", "minutes": 45}, 132)


def test_the_app_never_asks_for_a_checkin(tmp_path):
    conn = synced(tmp_path)
    for d in (ANCHOR, date(2026, 9, 21)):  # a typical day and the synthetic recovery dip
        assert rp.build_morning(conn, "fixture", d, True)["checkin_prompt"]["ask"] is False


def test_focus_is_picked_automatically_and_can_be_changed(tmp_path):
    conn = synced(tmp_path)
    cur = fc.current(conn, "fixture", ANCHOR)
    assert cur["current"] and cur["current"]["auto"] is True
    fc.choose(conn, fc.week_start(ANCHOR), "steady_volume")
    again = fc.current(conn, "fixture", ANCHOR)
    assert again["current"]["kind"] == "steady_volume" and again["current"]["auto"] is False


def test_intent_is_inferred_but_never_flags_meant_to_be_easy(tmp_path):
    conn = synced(tmp_path)
    set_zones(conn)
    r = rp.build_post_run(conn, "fixture", "fx-run-2026-09-30", True)  # fixture intervals on Wednesday
    assert r["intent"]["source"] == "inferred" and r["intent"]["kind"] == "intervals"
    easyish = rp.build_post_run(conn, "fixture", "fx-run-2026-09-28", True)
    assert easyish["intent"]["source"] == "inferred"
    assert not any(f["metric"] == "intent_vs_actual" for f in easyish["findings"])
