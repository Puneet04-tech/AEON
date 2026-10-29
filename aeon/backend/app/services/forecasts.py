"""Weather-driven capacity forecasts.

The weather is real (Open-Meteo, no API key). The dollar model that turns
temperature into an energy price factor is SIMULATED and labelled as such
everywhere it surfaces.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
import structlog

from app.services.pricing import energy_factor
from app.settings import settings

logger = structlog.get_logger()

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_KEY = "forecast:current"


async def _fetch_weather() -> dict:
    params = {
        "latitude": settings.WEATHER_LAT,
        "longitude": settings.WEATHER_LON,
        "hourly": "temperature_2m",
        "forecast_days": 1,
        "timezone": "UTC",
    }
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.get(OPEN_METEO_URL, params=params)
    response.raise_for_status()
    body = response.json()
    temps = (body.get("hourly") or {}).get("temperature_2m") or []
    if not temps:
        raise ValueError("no temperature data")
    now_hour = datetime.now(timezone.utc).hour
    window = [t for t in temps[now_hour:now_hour + 6] if t is not None] or [t for t in temps if t is not None]
    return {
        "source": "open-meteo",
        "hourly_temps_c": window[:6],
        "temp_c": round(sum(window[:6]) / max(1, len(window[:6])), 2),
    }


def _fallback() -> dict:
    return {"source": "fallback", "hourly_temps_c": [21.0] * 6, "temp_c": 21.0}


async def get_forecast(db, force: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    if not force:
        cached = await db.forecasts.find_one({"region_label": "Region A (simulated)"})
        if cached and cached.get("fetched_at"):
            fetched = cached["fetched_at"]
            if isinstance(fetched, str):
                fetched = datetime.fromisoformat(fetched)
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            if now - fetched < timedelta(seconds=settings.WEATHER_CACHE_SECONDS):
                return {**cached, "_id": None, "cached": True}

    try:
        weather = await _fetch_weather()
    except Exception as exc:  # offline demo must still work
        logger.warning("weather_fetch_failed", error=str(exc)[:160])
        weather = _fallback()

    factor = energy_factor(weather["temp_c"])
    doc = {
        "region_label": "Region A (simulated)",
        "fetched_at": now,
        "source": weather["source"],
        "payload_summary": {
            "temp_c": weather["temp_c"],
            "energy_factor": factor,
            "hourly_temps_c": weather["hourly_temps_c"],
        },
        "simulated_pricing": True,
        "cached": False,
    }
    await db.forecasts.update_one({"region_label": doc["region_label"]},
                                  {"$set": doc}, upsert=True)
    return doc


async def energy_factor_now(db) -> float:
    if not settings.ENABLE_FORECASTS:
        return 1.0
    try:
        forecast = await get_forecast(db)
        return float(forecast["payload_summary"]["energy_factor"])
    except Exception:  # never let a weather outage stop a trade
        return 1.0


async def region_outlook(db) -> List[dict]:
    forecast = await get_forecast(db)
    base = forecast["payload_summary"]["energy_factor"]
    outlook = []
    for region, multiplier_bps in (("Region A (simulated)", 10000),
                                   ("Region B (simulated)", 9200),
                                   ("Region C (simulated)", 11500)):
        outlook.append({
            "region_label": region,
            "region_multiplier_bps": multiplier_bps,
            "energy_factor": base,
            "temp_c": forecast["payload_summary"]["temp_c"],
            "source": forecast["source"],
            "simulated": True,
        })
    return outlook
