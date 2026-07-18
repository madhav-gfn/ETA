// Indian CPCB PM2.5 breakpoints (µg/m³) → category, color, guidance.
export interface AqiBand {
  max: number;
  label: string;
  color: string;
  text: string;
  guidance: string;
}

export const AQI_BANDS: AqiBand[] = [
  { max: 30, label: "Good", color: "#22c55e", text: "#052e16", guidance: "Air quality is satisfactory for everyone." },
  { max: 60, label: "Satisfactory", color: "#84cc16", text: "#1a2e05", guidance: "Sensitive groups may feel minor discomfort." },
  { max: 90, label: "Moderate", color: "#eab308", text: "#422006", guidance: "People with lung/heart disease should limit prolonged exertion." },
  { max: 120, label: "Poor", color: "#f97316", text: "#431407", guidance: "Everyone may experience discomfort on prolonged exposure." },
  { max: 250, label: "Very Poor", color: "#ef4444", text: "#450a0a", guidance: "Avoid outdoor activity; respiratory illness likely on prolonged exposure." },
  { max: Infinity, label: "Severe", color: "#881337", text: "#fff1f2", guidance: "Health emergency — stay indoors, use purifiers/masks." },
];

export function pm25Band(v: number): AqiBand {
  return AQI_BANDS.find((b) => v <= b.max) ?? AQI_BANDS[AQI_BANDS.length - 1];
}

export function pm25Color(v: number): string {
  return pm25Band(v).color;
}

export const CITIES = [
  { slug: "delhi-ncr", name: "Delhi NCR", live: true },
  { slug: "mumbai", name: "Mumbai", live: false },
  { slug: "bengaluru", name: "Bengaluru", live: false },
  { slug: "kolkata", name: "Kolkata", live: false },
  { slug: "chennai", name: "Chennai", live: false },
] as const;

export const LANGS = [
  { code: "en", label: "English", native: "English", live: true },
  { code: "hi", label: "Hindi", native: "हिन्दी", live: true },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ", live: false },
  { code: "ta", label: "Tamil", native: "தமிழ்", live: false },
  { code: "bn", label: "Bengali", native: "বাংলা", live: false },
  { code: "mr", label: "Marathi", native: "मराठी", live: false },
] as const;
