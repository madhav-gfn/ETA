"""
Step 7 — citizen health advisory (PS brief: "Citizen Health Risk Advisory
System ... in regional languages"). LLM-generated plain-language copy in
English or Hindi from the current gridded state, with a deterministic
template fallback so the card always renders.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.llm import complete
from app.core.db import get_db
from app.geospatial.models import GridReading
from app.ingestion.cities import DEFAULT_CITY, get_city

router = APIRouter(prefix="/advisory", tags=["advisory"])


def _aqi_category(pm25: float) -> str:
    if pm25 <= 30:
        return "Good"
    if pm25 <= 60:
        return "Satisfactory"
    if pm25 <= 90:
        return "Moderate"
    if pm25 <= 120:
        return "Poor"
    if pm25 <= 250:
        return "Very Poor"
    return "Severe"


FALLBACK = {
    "en": "PM2.5 in {city} is currently {value:.0f} µg/m³ ({category}). "
          "Sensitive groups (children, elderly, respiratory patients) should limit "
          "prolonged outdoor exertion. Prefer N95 masks outdoors and keep windows "
          "closed during peak traffic hours.",
    "hi": "{city} में PM2.5 वर्तमान में {value:.0f} µg/m³ ({category}) है। "
          "संवेदनशील समूह (बच्चे, बुज़ुर्ग, श्वसन रोगी) लंबे समय तक बाहरी परिश्रम "
          "से बचें। बाहर N95 मास्क पहनें और व्यस्त यातायात के समय खिड़कियाँ बंद रखें।",
}


@router.get("")
def get_advisory(
    city_slug: str = DEFAULT_CITY, lang: str = "en", db: Session = Depends(get_db)
):
    city = get_city(city_slug)
    latest_ts = db.execute(
        select(func.max(GridReading.measured_at)).where(
            GridReading.city_slug == city_slug, GridReading.parameter == "pm25"
        )
    ).scalar_one_or_none()

    if latest_ts is None:
        mean_pm25, max_pm25 = None, None
    else:
        mean_pm25, max_pm25 = db.execute(
            select(func.avg(GridReading.value), func.max(GridReading.value)).where(
                GridReading.city_slug == city_slug,
                GridReading.parameter == "pm25",
                GridReading.measured_at == latest_ts,
            )
        ).one()

    if mean_pm25 is None:
        return {"city_slug": city_slug, "lang": lang, "advisory": None,
                "detail": "No gridded readings yet"}

    category = _aqi_category(mean_pm25)
    lang = lang if lang in FALLBACK else "en"
    fallback_text = FALLBACK[lang].format(
        city=city.display_name, value=mean_pm25, category=category
    )
    language_name = "Hindi (Devanagari script)" if lang == "hi" else "English"
    llm_text = complete(
        system=(
            f"You are a public health communicator for an Indian city government. Write a "
            f"3-sentence citizen air quality advisory in {language_name}. Plain, calm, "
            f"actionable language for the general public — no jargon, no markdown."
        ),
        user=(
            f"City: {city.display_name}. Current mean PM2.5: {mean_pm25:.0f} µg/m³ "
            f"(category: {category}); worst grid cell: {max_pm25:.0f} µg/m³. "
            f"Measured at {latest_ts.isoformat()}."
        ),
        max_tokens=300,
    )
    return {
        "city_slug": city_slug,
        "lang": lang,
        "measured_at": latest_ts.isoformat(),
        "mean_pm25": round(mean_pm25, 1),
        "max_pm25": round(max_pm25, 1),
        "category": category,
        "advisory": llm_text or fallback_text,
        "llm_used": llm_text is not None,
    }
