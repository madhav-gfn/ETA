"""Indian CPCB PM2.5 breakpoint bands — shared by advisory + stats routes
(mirrors the frontend's lib/aqi.ts so both surfaces label values identically)."""

CPCB_BANDS = [
    (30, "Good"),
    (60, "Satisfactory"),
    (90, "Moderate"),
    (120, "Poor"),
    (250, "Very Poor"),
]


def cpcb_category(pm25: float) -> str:
    for upper, label in CPCB_BANDS:
        if pm25 <= upper:
            return label
    return "Severe"
