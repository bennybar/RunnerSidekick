"""Export polish from the 25 Oct 2026 Venu X1 run: Garmin's tail of metres-long laps is one partial split, the
efficiency trend says inconclusive inside its runs' own spread, and a slower second half becomes "start slower" only when
heat, the runner's own report and ordinary variation don't explain it."""

from datetime import date

from sidekick import progress
from sidekick import reports as rp
from sidekick.analytics import running as rn

# The run's laps as Garmin sent them: seven auto km laps, then 10.6 m and 7.5 m (a lap press just before stopping)
LAPS_25 = [{"idx": i, "distance_m": 1000.0, "elapsed_s": e, "moving_s": e, "avg_hr": h, "max_hr": h + 5, "elevation_gain_m": 9.0,
            "elevation_loss_m": 8.0} for i, (e, h) in enumerate(((355.5, 134), (343.5, 153), (334.0, 158), (341.3, 153), (362.8, 162),
                                                                (344.6, 160), (351.3, 163)))] + [
    {"idx": 7, "distance_m": 10.62, "elapsed_s": 3.565, "moving_s": 3.0, "avg_hr": 166, "max_hr": 167, "elevation_gain_m": 0.0, "elevation_loss_m": 0.0},
    {"idx": 8, "distance_m": 7.53, "elapsed_s": 2.611, "moving_s": 2.0, "avg_hr": 166, "max_hr": 168, "elevation_gain_m": 0.0, "elevation_loss_m": 1.0}]


def test_the_tail_of_short_laps_is_one_partial_without_a_pace():
    laps = rn.merge_short_tail(LAPS_25)
    assert len(laps) == 8 and laps[-1]["idx"] == 7
    assert round(laps[-1]["distance_m"], 2) == 18.15 and round(laps[-1]["elapsed_s"], 2) == 6.18 and laps[-1]["max_hr"] == 168
    splits = rn.splits_from_laps(laps)
    assert [s.complete for s in splits] == [True] * 7 + [False]
    assert splits[-1].pace_s_per_km is None  # 18 m: no pace worth showing
    assert all(s.pace_s_per_km for s in splits[:7])
    assert LAPS_25[-1]["distance_m"] == 7.53  # the stored laps aren't changed


def test_other_lap_patterns_are_left_alone():
    one_tail = LAPS_25[:8]  # a single partial at the end: as it was
    assert rn.merge_short_tail(one_tail) == one_tail
    intervals = [{"idx": i, "distance_m": d, "elapsed_s": 60.0} for i, d in enumerate((1500, 400, 200, 400, 200, 400, 200, 1000))]
    assert rn.merge_short_tail(intervals) == intervals  # not a run of auto km laps


def test_efficiency_within_its_own_spread_is_inconclusive(monkeypatch):
    paces = [351, 355, 359, 369, 339, 364, 357]  # the Venu X1's seven runs, 24 Sep – 25 Oct
    era = {"device": "venu", "runs": 7, "start": "2026-09-24", "end": "2026-10-25", "slope_s_per_km_per_30d": 11.7,
           "first_half_median_pace": 355, "second_half_median_pace": 360,
           "points": [{"date": f"2026-10-{i + 1:02d}", "pace_s_per_km": p} for i, p in enumerate(paces)]}
    body = {"insights": [{"id": "efficiency", "effect": {"band_bpm": [160, 169], "eras": [era]}}]}
    monkeypatch.setattr(rp, "latest_body", lambda conn, kind, *a: body if kind == "insights" else None)
    s = progress.efficiency_signal(None, "garmin", date(2026, 10, 25))
    assert s["direction"] == "inconclusive" and "±6 s/km" in s["say"]
    era["second_half_median_pace"] = 375  # a real slowdown, well beyond the spread
    assert progress.efficiency_signal(None, "garmin", date(2026, 10, 25))["direction"] == "declining"


def test_a_slower_second_half_is_read_in_context():
    splits = rn.splits_from_laps(rn.merge_short_tail(LAPS_25))
    gaps = [350, 336, 333, 347, 347, 346, 346, None]  # hill-adjusted s/km by km, as on 25 Oct
    details = [{"gap_pace_s_per_km": g, "zone": 4, "elevation_loss_m": 8.0} for g in gaps]
    an = {"classification": {"kind": "steady", "reason": "", "speed_cv": 0.05}}
    tempo = {"kind": "tempo", "source": "user", "feel": "great", "effort": "moderate", "limiter": "heat"}
    hot = {"hot": True, "say": "22°C, dew point 20°C"}
    focus = lambda intent, heat: rp.next_focus(an, {}, {}, splits, details, intent, None, 155, heat)  # noqa: E731
    assert "isn't clearly a pacing problem" in focus(tempo, hot)
    assert "no change needed" in focus(tempo, None)
    assert "start" not in focus(tempo, hot) and "start" not in focus(tempo, None)
    # No report and a cool day: a fade beyond the km-to-km variation is still called one
    faded = [{"gap_pace_s_per_km": g, "zone": 4} for g in (330, 330, 332, 331, 350, 352, 351, None)]
    assert "start" in rp.next_focus(an, {}, {}, splits, faded, {"kind": "tempo", "source": "user"}, None, 155, None)
