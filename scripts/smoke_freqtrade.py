"""Load and validate configuration with the actual pinned library; never trade."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pvb24.safety import require_paper  # noqa: E402


def main():
    import freqtrade
    from freqtrade.configuration import Configuration
    from freqtrade.configuration.config_validation import validate_config_consistency
    from freqtrade.enums import RunMode

    pin = json.loads((ROOT / "config/manifest.json").read_text())["freqtrade"]
    if freqtrade.__version__ != pin["version"]:
        raise SystemExit("Loaded Freqtrade version differs from pin")
    (ROOT / ".deps/smoke-user-data").mkdir(parents=True, exist_ok=True)
    cfg = Configuration(
        {
            "config": [str(ROOT / "integrations/freqtrade/config.dryrun.example.json")],
            "user_data_dir": str(ROOT / ".deps/smoke-user-data"),
        },
        RunMode.DRY_RUN,
    ).get_config()
    require_paper(cfg)
    validate_config_consistency(cfg)
    print(
        json.dumps(
            {
                "freqtrade_version": freqtrade.__version__,
                "config_loaded": True,
                "dry_run": True,
                "orders_submitted": 0,
                "operational_paper_ready": False,
            }
        )
    )


if __name__ == "__main__":
    main()
