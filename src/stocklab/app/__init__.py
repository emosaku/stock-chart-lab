"""App: Streamlit dashboard, read-only over storage.

Per-ticker candlestick chart with indicator overlays and signal markers, plus backtest
results and the latest model predictions with confidence. Never computes indicators
or trains models itself -- it shows what the pipeline stored. Phase 6; deploys to
Cloud Run as a container later.
"""
