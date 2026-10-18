"""Phase 0 smoke test: the package and every component import cleanly."""

import stocklab.app  # noqa: F401
import stocklab.backtesting  # noqa: F401
import stocklab.features  # noqa: F401
import stocklab.ingestion  # noqa: F401
import stocklab.models  # noqa: F401
import stocklab.signals  # noqa: F401
import stocklab.storage  # noqa: F401
from stocklab import config


def test_config_has_region():
    assert config.GCP_REGION
