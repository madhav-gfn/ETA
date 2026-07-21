-- Runs once on first container start (local Docker only — Supabase doesn't
-- run this file; run the CREATE EXTENSION line manually in its SQL editor,
-- see docs/DEPLOY.md).
-- Enables PostGIS so Step 3's 1km grid + IDW work can store geometry columns.
-- No postgis_topology: the grid is independent, non-adjacent cells with no
-- shared-boundary editing, so plain geometry (ST_Contains/ST_DWithin/
-- ST_Intersects) is all this project ever needs.

CREATE EXTENSION IF NOT EXISTS postgis;
