"""
Canonical feature-cube channel layout — a leaf module with no heavy imports
so the training path can run on a bare GPU box (Colab/Kaggle) with nothing
beyond numpy + torch installed.

Channel order is append-only: serving slices a cube down to the channel count
a checkpoint was trained with, so older models keep working after new
channels are added — as long as existing indices never move.
"""

CHANNELS = [
    "pm25", "pm10", "no2",
    "temperature", "humidity", "wind_speed", "wind_dir_sin", "wind_dir_cos",
    "fire_frp", "road_density", "industrial",
    # Diurnal-cycle encoding (UTC hour; the fixed IST phase shift is absorbed
    # by learned weights). Added 2026-07-19 so the model can see time of day —
    # without these, a 24h forecast can't exploit the daily PM2.5 cycle.
    "hod_sin", "hod_cos",
]
POLLUTANT_CHANNELS = {"pm25": 0, "pm10": 1, "no2": 2}

PM25_CH = CHANNELS.index("pm25")
HOD_SIN_CH = CHANNELS.index("hod_sin")
HOD_COS_CH = CHANNELS.index("hod_cos")
