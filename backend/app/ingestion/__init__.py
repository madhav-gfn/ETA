"""
Step 2 — Data Ingestion Layer.

Will contain one puller module per data modality from the research report's
Table 2:
  - caaqms_openaq.py   Hourly ground sensor pull via the OpenAQ SDK
  - firms_fires.py     3-hourly NASA FIRMS thermal anomaly pull
  - osm_landuse.py     Monthly static OSM Overpass land-use/road vectors
  - sentinel5p.py      Daily Sentinel-5P NO2/SO2 raster pull (NRTI + OFFL)

Each puller normalizes its source into a common schema and writes to Postgres
raw tables. A scheduler (APScheduler) module here will trigger pulls at the
cadence each source requires.
"""
