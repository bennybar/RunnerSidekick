"""Small builders for test data written straight to the user database."""


def add_checkin(conn, cid, local_date, energy=None, soreness=None, recovery=None, pain=False, illness=False, notes=None, updated="x"):
    conn.checkin.replace_one({"id": cid}, {"id": cid, "local_date": local_date, "energy": energy, "soreness": soreness, "recovery": recovery,
                                           "pain": pain, "illness": illness, "notes": notes, "tags": [], "client_updated_at": updated,
                                           "received_at": "x", "deleted": False}, upsert=True)


def set_plan(conn, local_date, kind, minutes):
    conn.day_plan.replace_one({"local_date": local_date}, {"local_date": local_date, "kind": kind, "minutes": minutes,
                                                           "client_updated_at": "x"}, upsert=True)
