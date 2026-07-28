"""Hermetic pytest defaults for the regression suite."""
from __future__ import annotations

import os


# LiteLLM otherwise fetches its model-price map during import. Tests use
# stubbed provider calls and must never depend on live network availability.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/poly-matplotlib")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/poly-cache")
