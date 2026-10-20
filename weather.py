"""Været for dagen fra Open-Meteo (gratis, ingen konto eller nøkkel; bare koordinatene sendes).

Stedet velges under ⚙ → weather (søk etter by). Uten valgt sted hentes ingenting.
Kalles fra bakgrunnstråder; ikonene er små pixel-sprites i samme stil som katten.
"""
import json
import urllib.parse
import urllib.request

GEOCODING = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

# WMO-værkoder -> type (https://open-meteo.com/en/docs)
KINDS = [
    ((0,), "clear"), ((1, 2), "partly"), ((3,), "cloudy"), ((45, 48), "fog"),
    ((51, 53, 55, 56, 57), "drizzle"), ((61, 63, 65, 66, 67, 80, 81, 82), "rain"),
    ((71, 73, 75, 77, 85, 86), "snow"), ((95, 96, 99), "thunder"),
]

# Ikoner som fyll (y = sol, g = sky, u = regn, W = snø, m = måne); konturen legges på som for katten
_CLOUD = ["..gg.....", ".gggg.gg.", "ggggggggg", "ggggggggg"]
ICONS = {
    "clear": ["...y...", ".y.y.y.", "..yyy..", "yyyyyyy", "..yyy..", ".y.y.y.", "...y..."],
    "night": ["..mmm..", ".mm....", "mm.....", "mm.....", "mm.....", ".mm....", "..mmm.."],
    "partly": ["yy.......", "yy.gg....", "y.gggg.gg", ".gggggggg", "ggggggggg"],
    "cloudy": _CLOUD,
    "fog": ["ggggggggg", ".........", ".ggggggg.", ".........", "ggggggggg"],
    "drizzle": _CLOUD + [".u...u...", "...u...u."],
    "rain": _CLOUD + ["u.u.u.u..", ".u.u.u.u.", "u.u.u.u.."],
    "snow": _CLOUD + ["W..W..W..", ".W..W..W."],
    "thunder": _CLOUD + ["...yy....", "..yy.....", ".yy......"],
}
COLORS = {"y": "#ffc93c", "g": "#c9ccd3", "u": "#5aa9e6", "W": "#ffffff", "m": "#e8e0b0", "o": "#2b2b33"}


def kind(code, is_day=True):
    for codes, name in KINDS:
        if code in codes:
            return "night" if name == "clear" and not is_day else name
    return "cloudy"


def _get(url, params):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "morgen-todo"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def search(name, language="en"):
    """Steder som passer navnet: [{name, region, country, lat, lon}]."""
    data = _get(GEOCODING, {"name": name, "count": 6, "language": language, "format": "json"})
    return [{"name": r["name"], "region": r.get("admin1", ""), "country": r.get("country", ""),
             "lat": r["latitude"], "lon": r["longitude"]} for r in data.get("results", [])]


def parse(data):
    cur, day = data["current"], data["daily"]
    return {
        "temp": round(cur["temperature_2m"]),
        "kind": kind(cur["weather_code"], bool(cur.get("is_day", 1))),
        "day_kind": kind(day["weather_code"][0]),
        "min": round(day["temperature_2m_min"][0]),
        "max": round(day["temperature_2m_max"][0]),
        "rain": day.get("precipitation_probability_max", [None])[0],
    }


def fetch(lat, lon):
    """Været nå og for i dag."""
    return parse(_get(FORECAST, {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,weather_code,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    }))


def remark(w):
    """Hva katten sier om dagens vær om morgenen (engelsk nøkkel, oversettes av vinduet), eller None."""
    if w["day_kind"] in ("rain", "drizzle", "thunder") and (w["rain"] or 0) >= 50:
        return "take an umbrella! ☔"
    if w["day_kind"] == "snow":
        return "snow! ❄"
    if w["day_kind"] in ("clear", "partly") and w["max"] >= 18:
        return "nice day! ☀"
    return None
