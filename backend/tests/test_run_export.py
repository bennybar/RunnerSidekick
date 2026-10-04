from datetime import date

from sidekick import reports as rp
from sidekick import run_export
from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, next_id, user_db_name, utc_now
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


def test_export_has_every_section_and_the_ai_input_last():
    conn = connect(user_db_name(1, "fixture"))
    run_sync(conn, FixtureConnector(ANCHOR), ANCHOR, 45, 3, max_backfill_days=60)
    sid = rp.activities(conn, "fixture", "2026-09-01", ANCHOR.isoformat())[-1]["source_id"]
    name, md = run_export.markdown(conn, "fixture", sid)
    assert name.endswith("-running.md") and md.startswith("# Running")
    for section in ("## How it went", "## Pace and splits", "## Decoupling (heart-rate drift)", "## Minute by minute", "## AI input"):
        assert section in md, section
    assert "No AI input for this run yet." in md
    conn.run_ai.insert_one({"id": next_id(conn, "run_ai"), "source_id": sid, "input_hash": "x", "model": "m", "status": "ok",
                            "output": {"tldr": "Solid run.", "summary": "Even effort.", "went_well": [{"text": "Pacing"}],
                                       "to_work_on": [], "next_time": {"text": "Keep it easy.", "direction": "easier"}},
                            "created_at": utc_now()})
    _, md = run_export.markdown(conn, "fixture", sid)
    tail = md[md.index("## AI input"):]
    assert "**TL;DR:** Solid run." in tail and "### Went well" in tail and "Keep it easy." in tail
    assert md.index("## AI input") > md.index("## Minute by minute")  # the AI input comes last
    assert run_export.markdown(conn, "fixture", "nope") is None
