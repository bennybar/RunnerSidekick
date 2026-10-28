from datetime import date

from sidekick import health

D = date(2026, 10, 28)


class Obs:
    """daily_observation with a few stored values (Body Battery, stress) for the 7-day lines."""
    def __init__(self, rows=()):
        self.rows = list(rows)

    def find(self, q, _proj=None):
        lo, hi = q["local_date"]["$gte"], q["local_date"]["$lte"]
        return [r for r in self.rows if r["metric"] == q["metric"] and lo <= r["local_date"] <= hi]


class Conn:
    def __init__(self, rows=()):
        self.daily_observation = Obs(rows)


def f(metric, value, status, delta=None, spark=()):
    return {"metric": metric, "observed": {"value": value}, "status": status, "delta": {"abs": delta} if delta is not None else None,
            "sparkline": [{"date": d, "value": v} for d, v in spark]}


def ctx(metric, value):
    return {"metric": metric, "value": value, "unit": "", "label": None, "origin": "Garmin"}


def by_id(card):
    return {r["id"]: r for r in card["rows"]}


def test_a_usual_night_reads_as_slept_well_and_recovered_as_usual():
    body = {"findings": [f("sleep_duration", 7.5 * 3600, "within", spark=[("2026-10-27", 7 * 3600), ("2026-10-28", 7.5 * 3600)]),
                         f("hrv_overnight_avg", 46, "within"), f("resting_hr", 50, "within")],
            "garmin_context": [ctx("garmin_sleep_score", 84), ctx("body_battery_high", 78), ctx("body_battery_low", 17), ctx("avg_stress", 17)]}
    card = health.build(body, Conn([{"metric": "avg_stress", "local_date": "2026-10-28", "value": 17}]), "garmin", D)
    assert card["headline"] == "Slept well, recovered as usual."
    r = by_id(card)
    assert [x["id"] for x in card["rows"]] == ["sleep", "hrv", "resting_hr", "body_battery", "stress"]
    assert r["sleep"]["value"] == "7 h 30 min" and r["sleep"]["detail"] == "score 84, good" and r["sleep"]["status"] == "usual"
    assert r["sleep"]["spark"] == [None] * 5 + [7 * 3600, 7.5 * 3600]
    assert r["hrv"]["value"] == "46 ms" and r["hrv"]["detail"] == "as usual"
    assert r["body_battery"]["value"] == "17 → 78" and r["body_battery"]["status"] == "good"
    assert r["stress"]["value"] == "17 avg" and r["stress"]["detail"] == "restful (Garmin)" and r["stress"]["spark"][-1] == 17


def test_direction_decides_good_or_watch():
    body = {"findings": [f("sleep_duration", 6.5 * 3600, "within"), f("hrv_overnight_avg", 60, "outside", 12),
                         f("resting_hr", 56, "outside", 5)], "garmin_context": []}
    r = by_id(health.build(body, Conn(), "garmin", D))
    # Higher HRV is better, a higher resting heart rate is not
    assert r["hrv"]["status"] == "good" and r["hrv"]["detail"] == "above your usual"
    assert r["resting_hr"]["status"] == "watch"
    # Within your own range but under the 7 hours most adults need
    assert r["sleep"]["status"] == "usual" and "short of 7 h" in r["sleep"]["detail"]
    assert health.build(body, Conn(), "garmin", D)["headline"] == "Sleep a bit short, one recovery signal is off."


def test_missing_and_learning_nights_say_so():
    body = {"findings": [f("sleep_duration", None, "missing"), f("hrv_overnight_avg", 40, "learning"), f("resting_hr", None, "missing")],
            "garmin_context": []}
    card = health.build(body, Conn(), "garmin", D)
    assert card["headline"] == "Last night isn't in yet, recovery still being learned."
    assert by_id(card)["sleep"]["value"] is None and by_id(card)["sleep"]["status"] == "missing"


def test_garmin_bands_for_stress_and_battery():
    body = {"findings": [], "garmin_context": [ctx("avg_stress", 60), ctx("body_battery_high", 40)]}
    r = by_id(health.build(body, Conn(), "garmin", D))
    assert r["stress"]["detail"] == "medium (Garmin)" and r["stress"]["status"] == "watch"
    assert r["body_battery"]["value"] == "40" and r["body_battery"]["status"] == "watch"
    assert health.build({"findings": [], "garmin_context": []}, Conn(), "garmin", D) is None
