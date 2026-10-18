"""Models: ML predictions with honest evaluation.

Targets: next-day direction (up/down) and next-5-day volatility. Naive baselines,
logistic regression, then XGBoost, all scored with walk-forward validation only
(train on the past, test on the following window, roll forward). Writes predictions
with confidence to the predictions table. Phase 5.
"""
