# Demo Script & Presentation Outline

## Demo script (follows the data flow, ~4 minutes)

1. **Live digital twin** — open the dashboard: 2,805 one-km cells over Delhi
   NCR, colored by IDW-interpolated PM2.5 from live OpenAQ/CAAQMS sensors.
   Click a cell → its value appears; note the "live snapshot" timestamp.
2. **Forecast slider** — step +1h → +72h: ConvLSTM rollout re-colors the
   grid. Point at the metrics chip: **24h RMSE 33.7 vs persistence 34.4 —
   beats the baseline** (the PS brief's literal evaluation metric), on 320
   held-out chronological windows. At 1h the model ties persistence (19.10
   vs 19.09) — say so if asked: hourly PM2.5 is strongly autocorrelated, so
   1h persistence is nearly unbeatable; the intervention-relevant horizon
   is 24h+, where the model wins.
3. **Anomaly drill** — click *Run anomaly drill* (synthetic anomaly, honestly
   flagged "drill"). Watch the LangGraph pipeline return:
   - the alert cell ringed on the map,
   - **attribution** with evidence (upwind FIRMS fires in a 60° wind cone,
     industrial/highway density) and a Groq-written forensic rationale,
   - the **patrol route** (exposure-ranked cells, nearest-neighbour chain)
     drawn on the map with dispatch instructions.
4. **Citizen advisory** — toggle English → हिन्दी: LLM-generated advisory from
   the same grid state (regional-language ask from the PS brief).
5. Close on the architecture diagram: same pipeline, second city = one bbox
   line in `cities.py`.

## Deck outline (mapped to judging weights)

| Slide | Criterion (weight) | Content / artifact |
|---|---|---|
| 1 | — | Title + one-line thesis: "The data exists. The intelligence layer to act on it does not." |
| 2 | Business Impact (25%) | 1.67M premature deaths/yr; 24 of 50 most-polluted cities Tier 1/2; only 31% of monitored cities have response protocols (CAG 2024). What this closes: signal → intervention. |
| 3 | Technical Excellence (25%) | Architecture diagram (docs/ARCHITECTURE.md); 4 live-verified ingestion pipelines; RMSE-vs-persistence table from `/forecast/metrics`. |
| 4 | Technical Excellence | Agent pipeline anatomy: real evidence objects (FIRMS FRP, OSM density, wind cone) + LLM rationale with deterministic fallback. |
| 5 | Scalability (20%) | `cities.py` — Mumbai already registered; grid, cubes, model, agents all keyed by `city_slug`. Docker Compose → Render, Next.js → Vercel. |
| 6 | Innovation (15%) | Most AQI dashboards stop at monitoring. This closes the loop: fused attribution → prioritised enforcement route → bilingual citizen advisory. |
| 7 | User Experience (15%) | Dashboard walkthrough screenshots: heatmap, slider, drill, Hindi toggle. |
| 8 | — | Honest limitations & roadmap: S5P raster regridding slot (NaN-flagged channel already in the cube), Kriging upgrade, OSRM road-network routing, IVR delivery. |

## Honest-limitations notes (judges ask)

- Sentinel-5P is catalog-ingested; raster regridding is a documented slot in
  the cube (`no2` channel), currently filled by ground-sensor IDW.
- July demo = monsoon: zero real fires near Delhi (verified live) — hence the
  synthetic drill, clearly flagged `synthetic: true` end-to-end.
- Patrol route is nearest-neighbour over centroids, not road-network routing;
  OSRM is the drop-in upgrade.
