# Architecture — UrbanAir Intel

```mermaid
flowchart LR
    subgraph Sources["External data sources"]
        OAQ["OpenAQ v3<br/>(CAAQMS proxy, hourly)"]
        FIRMS["NASA FIRMS<br/>(fires, 3-hourly)"]
        OM["Open-Meteo<br/>(wind/temp/RH, hourly)"]
        OSM["OSM Overpass<br/>(land use, monthly)"]
        S5P["Copernicus CDSE<br/>(Sentinel-5P catalog, daily)"]
    end

    subgraph Backend["FastAPI backend (backend/app)"]
        ING["ingestion/*<br/>pullers + APScheduler"]
        GRID["geospatial/*<br/>1km UTM grid + IDW"]
        CUBE["features/cube.py<br/>11-channel (H,W,C) tensors"]
        MODEL["models/*<br/>ConvLSTM + rollout"]
        AGENTS["agents/graph.py<br/>LangGraph: monitor→attribute→enforce"]
        ADV["advisory<br/>LLM citizen copy (en/hi)"]
    end

    subgraph Store["PostGIS (Docker, :5433)"]
        RAW[("raw readings<br/>fires / osm / meteo / s5p")]
        GC[("grid_cells /<br/>grid_readings")]
        MAN[("cube manifest /<br/>agent_runs")]
    end

    subgraph Frontend["Next.js dashboard (frontend/)"]
        MAP["Leaflet AQI heatmap<br/>+ forecast slider"]
        ENF["Enforcement panel"]
        CARD["Health advisory (en/हि)"]
    end

    OAQ & FIRMS & OM & OSM & S5P --> ING --> RAW
    RAW --> GRID --> GC
    RAW & GC --> CUBE --> MAN
    MAN --> MODEL
    MODEL -->|"/forecast/grid"| MAP
    GC -->|"/grid/readings"| MAP
    RAW & GC --> AGENTS -->|"/agents/*"| ENF
    GC --> ADV -->|"/advisory"| CARD
    LLM["Groq LLM<br/>(deterministic fallback)"] -.-> AGENTS & ADV
```

Folder ↔ box mapping: every box names its implementing module. The grid
(`grid_cells.row_idx/col_idx`) is the shared spatial index — ingestion output,
feature cubes, forecasts, and agent output all address cells by the same
`grid_id`, which is what makes adding a second city a one-line bbox change in
`ingestion/cities.py`.
