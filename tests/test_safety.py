import copy
import json
from pathlib import Path

import pytest

from pvb24.safety import require_paper

CONFIG = json.loads(
    (
        Path(__file__).resolve().parents[1] / "integrations/freqtrade/config.dryrun.example.json"
    ).read_text()
)


def test_paper_configuration_is_accepted():
    require_paper(CONFIG)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dry_run", False),
        ("dry_run", "true"),
        ("live_enabled", True),
        ("force_entry_enable", True),
        ("margin_mode", "cross"),
    ],
)
def test_unsafe_configuration_rejected(field, value):
    config = copy.deepcopy(CONFIG)
    config[field] = value
    with pytest.raises(ValueError):
        require_paper(config)


def test_credentials_rejected():
    config = copy.deepcopy(CONFIG)
    config["exchange"]["api_key"] = "synthetic-test-value"
    with pytest.raises(ValueError, match="credentials"):
        require_paper(config)
