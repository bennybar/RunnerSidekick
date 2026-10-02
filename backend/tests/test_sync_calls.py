from datetime import date

from sidekick.connectors.fixture import FixtureConnector
from sidekick.db import connect, user_db_name
from sidekick.sync import run_sync

ANCHOR = date(2026, 9, 30)


class Counting(FixtureConnector):
    """The fixture connector, recording which days and activity ranges were requested."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.days, self.lists, self.extra = [], [], 0

    def read_days(self, start, end):
        self.days.append((start, end))
        return super().read_days(start, end)

    def list_activities(self, start, end):
        self.lists.append(start)
        return super().list_activities(start, end)

    def fitness_snapshot(self, day):
        self.extra += 1
        return {"vo2max": {"value": 46.0}}

    def hr_zones(self):
        self.extra += 1
        return None

    def profile(self):
        self.extra += 1
        return None


def test_repeat_sync_skips_complete_days_and_rare_calls():
    conn = connect(user_db_name(1, "fixture"))
    first = Counting(ANCHOR)
    run_sync(conn, first, ANCHOR, 45, 3, max_backfill_days=60)
    again = Counting(ANCHOR)
    res = run_sync(conn, again, ANCHOR, 45, 3, max_backfill_days=60)
    assert res.outcome == "ok"
    fetched = {s for s, _ in again.days}
    # Today and yesterday are always re-read; older days of the window only if a core reading is missing
    assert {ANCHOR, date(2026, 9, 29)} <= fetched and len(fetched) <= 4
    # The activity list is the last week only, and fitness, zones and profile aren't asked again straight away
    assert again.lists and min(again.lists) >= date(2026, 9, 23) and again.extra == 0
