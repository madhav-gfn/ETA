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
from app.core.aqi import cpcb_category
from app.core.db import get_db
from app.geospatial.models import GridReading
from app.ingestion.cities import DEFAULT_CITY, get_city

router = APIRouter(prefix="/advisory", tags=["advisory"])

# (city, lang, latest_ts) -> response; the timestamp key self-invalidates when
# a new hour materializes. FIFO-capped, single-instance scope like the rest of
# the serving caches.
_ADVISORY_CACHE: dict[tuple[str, str, str], dict] = {}
_ADVISORY_CACHE_MAX = 256

# What the LLM is asked to write in; keys double as the set of accepted langs.
LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (Devanagari script)",
    "kn": "Kannada (Kannada script)",
    "ta": "Tamil (Tamil script)",
    "bn": "Bengali (Bengali script)",
    "mr": "Marathi (Devanagari script)",
}

FALLBACK = {
    "en": "PM2.5 in {city} is currently {value:.0f} µg/m³ ({category}). "
          "Sensitive groups (children, elderly, respiratory patients) should limit "
          "prolonged outdoor exertion. Prefer N95 masks outdoors and keep windows "
          "closed during peak traffic hours.",
    "hi": "{city} में PM2.5 वर्तमान में {value:.0f} µg/m³ ({category}) है। "
          "संवेदनशील समूह (बच्चे, बुज़ुर्ग, श्वसन रोगी) लंबे समय तक बाहरी परिश्रम "
          "से बचें। बाहर N95 मास्क पहनें और व्यस्त यातायात के समय खिड़कियाँ बंद रखें।",
    "kn": "{city} ನಲ್ಲಿ PM2.5 ಪ್ರಸ್ತುತ {value:.0f} µg/m³ ({category}) ಇದೆ. "
          "ಸೂಕ್ಷ್ಮ ಗುಂಪುಗಳು (ಮಕ್ಕಳು, ವೃದ್ಧರು, ಉಸಿರಾಟದ ರೋಗಿಗಳು) ದೀರ್ಘಕಾಲದ ಹೊರಾಂಗಣ "
          "ಶ್ರಮವನ್ನು ಮಿತಿಗೊಳಿಸಬೇಕು. ಹೊರಗೆ N95 ಮಾಸ್ಕ್ ಧರಿಸಿ ಮತ್ತು ದಟ್ಟಣೆಯ "
          "ಸಮಯದಲ್ಲಿ ಕಿಟಕಿಗಳನ್ನು ಮುಚ್ಚಿಡಿ.",
    "ta": "{city} இல் PM2.5 தற்போது {value:.0f} µg/m³ ({category}) ஆக உள்ளது. "
          "உணர்திறன் மிக்க குழுக்கள் (குழந்தைகள், முதியவர்கள், சுவாச நோயாளிகள்) "
          "நீண்ட நேர வெளிப்புற உழைப்பைக் குறைக்க வேண்டும். வெளியில் N95 முகக்கவசம் "
          "அணியுங்கள்; போக்குவரத்து நெரிசல் நேரங்களில் ஜன்னல்களை மூடி வையுங்கள்.",
    "bn": "{city}-এ PM2.5 বর্তমানে {value:.0f} µg/m³ ({category})। "
          "সংবেদনশীল গোষ্ঠী (শিশু, প্রবীণ, শ্বাসকষ্টের রোগী) দীর্ঘ সময় বাইরের "
          "পরিশ্রম সীমিত রাখুন। বাইরে N95 মাস্ক পরুন এবং ব্যস্ত যানবাহনের সময় "
          "জানালা বন্ধ রাখুন।",
    "mr": "{city} मध्ये PM2.5 सध्या {value:.0f} µg/m³ ({category}) आहे. "
          "संवेदनशील गट (लहान मुले, वृद्ध, श्वसन रुग्ण) दीर्घकाळ बाहेरील श्रम "
          "टाळावेत. बाहेर N95 मास्क वापरा आणि वाहतूक गर्दीच्या वेळी खिडक्या "
          "बंद ठेवा.",
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

    category = cpcb_category(mean_pm25)
    lang = lang if lang in FALLBACK else "en"

    # The gridded state only changes when a new hour materializes — reuse the
    # LLM copy until then instead of paying for a fresh call per page load.
    cache_key = (city_slug, lang, latest_ts.isoformat())
    cached = _ADVISORY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    fallback_text = FALLBACK[lang].format(
        city=city.display_name, value=mean_pm25, category=category
    )
    language_name = LANGUAGE_NAMES[lang]
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
    result = {
        "city_slug": city_slug,
        "lang": lang,
        "measured_at": latest_ts.isoformat(),
        "mean_pm25": round(mean_pm25, 1),
        "max_pm25": round(max_pm25, 1),
        "category": category,
        "advisory": llm_text or fallback_text,
        "llm_used": llm_text is not None,
    }
    if llm_text is not None:  # don't pin a degraded fallback until the next hour
        if len(_ADVISORY_CACHE) >= _ADVISORY_CACHE_MAX:
            _ADVISORY_CACHE.pop(next(iter(_ADVISORY_CACHE)))
        _ADVISORY_CACHE[cache_key] = result
    return result
