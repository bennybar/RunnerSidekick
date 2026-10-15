from datetime import date

from sidekick import reports as rp
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, set_setting, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def setup():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 60, 3, max_backfill_days=90)
    set_setting(conn, "source_hr_zones", {"floors": [95, 113, 132, 151, 170], "method": "HR_MAX", "max_hr": 189})
    a = max(rp.activities(conn, "fixture", "2026-01-01", ANCHOR.isoformat()), key=lambda x: x["start_utc"])
    return conn, a


def intend(conn, a, kind, **extra):
    conn.run_intent.replace_one({"activity_source_id": a["source_id"]}, {"activity_source_id": a["source_id"], "kind": kind, "note": None,
                                                                        "source": "user", **extra}, upsert=True)
    return rp.build_post_run(conn, "fixture", a["source_id"], True)["verdict"]


def test_no_intent_no_judgement_and_an_easy_run_judged_on_its_zones():
    conn, a = setup()
    assert rp.build_post_run(conn, "fixture", a["source_id"], True)["verdict"]["verdict"] == "not_enough_data"  # never the inferred type
    v = intend(conn, a, "easy")
    assert v["verdict"] in ("on_target", "harder") and "below zone 3" in v["say"] and v["basis"] == "your intent for the run"


def test_shortened_against_the_plan_and_a_heart_rate_cap():
    conn, a = setup()
    conn.run_intent.delete_many({})
    conn.day_plan.replace_one({"local_date": a["local_date"]}, {"local_date": a["local_date"], "kind": "easy", "minutes": 600}, upsert=True)
    v = rp.build_post_run(conn, "fixture", a["source_id"], True)["verdict"]
    assert v["verdict"] == "shortened" and v["basis"] == "the day's plan"
    conn.day_plan.delete_many({})
    assert intend(conn, a, "easy", target="HR <= 100")["verdict"] == "harder"  # the fixture runs well above 100 bpm
    assert intend(conn, a, "easy", target="HR <= 230")["verdict"] == "on_target"


def test_a_race_is_age_graded_only_at_a_standard_distance():
    conn, a = setup()
    set_setting(conn, "profile_sex", "male")
    set_setting(conn, "profile_birth_date", "1980-01-01")
    conn.activity.update_one({"source_id": a["source_id"]}, {"$set": {"distance_m": 6000.0, "elapsed_s": 1800.0}})
    v = intend(conn, a, "race")
    assert v["verdict"] == "race" and v["say"].startswith("No age grade: not a standard distance")
    conn.activity.update_one({"source_id": a["source_id"]}, {"$set": {"distance_m": 5000.0, "elapsed_s": 1500.0}})
    v = intend(conn, a, "race", note="x")  # a change to the intent rebuilds the report
    assert v["distance"] == "5k" and 0 < v["age_grade"]["age_grade_pct"] < 100 and "25:00" in v["say"]


def test_the_export_says_how_it_went():
    from sidekick import run_export
    conn, a = setup()
    intend(conn, a, "easy", target="HR <= 100")
    md = run_export.markdown(conn, "fixture", a["source_id"], fetch=lambda *x, **k: None)[1]
    assert "How it went: **Harder than planned** (judged as easy, from your intent for the run)" in md
