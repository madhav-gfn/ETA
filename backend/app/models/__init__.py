"""
Step 5 — Hyperlocal Predictive Forecasting Model.

Will contain:
  - convlstm.py    ConvLSTM architecture for 24-72hr grid-resolution AQI
                   forecasting (video-frame-style spatial forecasting).
  - baseline.py    Gradient-boosted per-grid-cell fallback if ConvLSTM
                   training time is constrained.
  - inference.py   Loads the trained checkpoint and serves predictions;
                   backs the /forecast/{grid_id} API route.
  - evaluate.py    RMSE vs persistence-baseline evaluation harness.
"""
