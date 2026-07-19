"""
Step 6 — Multi-Agent Intelligence Layer (LangGraph).

Will contain the agent graph described in the research report's Section 4:
  - monitoring_agent.py     Watches the forecast tensor for WHO-threshold
                            breaches, emits an Anomaly Alert payload.
  - attribution_agent.py    Cross-references FIRMS upwind fires, OSM
                            industrial zones, NO2 anomalies, and traffic
                            timing to score the likely pollution source.
  - enforcement_agent.py    Ranks grid cells by AQI x residential density
                            and drafts an inspector patrol route.
  - graph.py                Wires the above into a LangGraph state graph.
"""
