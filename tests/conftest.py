import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from scripts.make_demo import make_bundle  # noqa: E402
from verdict.config import ReviewConfig  # noqa: E402
from verdict.pipeline import review_bundle  # noqa: E402


@pytest.fixture
def bundle():
    return make_bundle("pass")


@pytest.fixture
def config():
    return ReviewConfig.from_env(model_required=False, model_scenario="valid_clean")


@pytest.fixture
def review(bundle, config):
    return review_bundle(bundle, config, use_cache=False)
