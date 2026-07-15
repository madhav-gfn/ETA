-- Runs once on first container start.
-- Enables PostGIS so Step 3's 1km grid + IDW work can store geometry columns.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
