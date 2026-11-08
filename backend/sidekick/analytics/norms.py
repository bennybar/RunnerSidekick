"""Published population references, copied verbatim from their sources. No values here are estimated by the app.

VO2 max: The Cooper Institute, as reprinted (with permission) in Garmin's "VO2 Max. Standard Ratings" table,
  https://www8.garmin.com/manuals/webhelp/GUID-C001C335-A8EC-4A41-AB0E-BAC434259F92/EN-US/GUID-1FBCCD9E-19E1-4E4C-BD60-1793B5B97EB3.html
  Values are the lower bound (mL/kg/min) of each rating: Fair = 40th, Good = 60th, Excellent = 80th, Superior = 95th percentile.
Resting heart rate: Ostchega Y et al. Resting pulse rate reference data for children, adolescents, and adults:
  United States, 1999–2008. National Health Statistics Reports No. 41, CDC/NCHS, 2011, Tables 2 (males) and 3 (females).
  https://www.cdc.gov/nchs/data/nhsr/nhsr041.pdf  (seated, after ~4 min rest, counted for 30 s; people with conditions
  or medication affecting pulse excluded). Percentiles 2.5–97.5 (1st/99th omitted: not reported for every group).
"""

from __future__ import annotations

import json
from pathlib import Path

VO2_SOURCE = "The Cooper Institute (as published in Garmin's VO2 max standard ratings)"
VO2_PERCENTILES = (40, 60, 80, 95)
VO2_RATINGS = ("Fair", "Good", "Excellent", "Superior")  # below the 40th percentile Garmin calls it "Poor"
VO2_BANDS = ((20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79))
VO2 = {
    "male": [(41.7, 45.4, 51.1, 55.4), (40.5, 44.0, 48.3, 54.0), (38.5, 42.4, 46.4, 52.5), (35.6, 39.2, 43.4, 48.9),
             (32.3, 35.5, 39.5, 45.7), (29.4, 32.3, 36.7, 42.1)],
    "female": [(36.1, 39.5, 43.9, 49.6), (34.4, 37.8, 42.4, 47.4), (33.0, 36.3, 39.7, 45.3), (30.1, 33.0, 36.7, 41.1),
               (27.5, 30.0, 33.0, 37.8), (25.9, 28.1, 30.9, 36.7)],
}

RHR_SOURCE = "US national survey (NHANES 1999–2008), CDC National Health Statistics Report 41"
RHR_PERCENTILES = (2.5, 5, 10, 25, 50, 75, 90, 95, 97.5)
RHR_BANDS = ((20, 39), (40, 59), (60, 79), (80, 120))
RHR = {
    "male": [(50, 52, 55, 61, 69, 76, 84, 89, 95), (49, 52, 55, 61, 68, 77, 85, 90, 95), (48, 50, 54, 60, 67, 75, 84, 91, 98),
             (48, 51, 54, 61, 68, 78, 86, 94, 97)],
    "female": [(55, 57, 60, 66, 74, 82, 89, 95, 99), (53, 56, 59, 64, 71, 79, 86, 92, 97), (54, 56, 59, 64, 70, 78, 86, 92, 96),
               (53, 56, 59, 64, 71, 77, 85, 93, 98)],
}

_AGE_STD = None


def age_standards() -> dict:
    """USATF MLDR 2025 road age standards (seconds), see data/age_standards_2025.json for the source."""
    global _AGE_STD
    if _AGE_STD is None:
        _AGE_STD = json.loads((Path(__file__).parent / "data" / "age_standards_2025.json").read_text())
    return _AGE_STD


def band_index(bands, age: int) -> tuple[int, bool]:
    """Index of the band containing age; outside the table the nearest band is used (second value: True if so)."""
    for i, (lo, hi) in enumerate(bands):
        if lo <= age <= hi:
            return i, False
    return (0 if age < bands[0][0] else len(bands) - 1), True


def percentile_of(value: float, points: tuple, percentiles: tuple) -> tuple[float | None, str]:
    """Position of value among published percentile points, by straight-line interpolation between neighbouring
    points. Outside the published range returns None with 'below'/'above' (never extrapolated)."""
    if value < points[0]:
        return None, "below"
    if value > points[-1]:
        return None, "above"
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if a <= value <= b:
            f = 0.0 if b == a else (value - a) / (b - a)
            return percentiles[i] + f * (percentiles[i + 1] - percentiles[i]), "within"
    return float(percentiles[-1]), "within"
