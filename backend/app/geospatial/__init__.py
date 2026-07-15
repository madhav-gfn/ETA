"""
Step 3 — Geospatial Grid Engine (digital twin core).

Will contain:
  - grid.py   Defines the 1km x 1km PostGIS grid over a city bounding box
              (EPSG:32643 for North India) and grid <-> lat/lon lookups.
  - idw.py    Inverse Distance Weighting interpolation projecting irregular
              CAAQMS point readings onto grid centroids per hour.

Every later step (feature fusion, forecasting, agents) reads/writes against
the grid defined here.
"""
