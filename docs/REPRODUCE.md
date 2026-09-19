# Tested reproduction commands

Working directory: repository root, branch build/pvb24-v1. Python 3.12.14.

The following commands completed successfully with exit code 0 in this workspace:

```bash
python -m pip install ruff==0.16.3 pytest==8.4.2 --disable-pip-version-check
python -m ruff format --check .
python -m ruff check .
python -m pytest -q
python scripts/verify_provenance.py
```

Nine governance tests passed. No static type checker configured at Milestone 0.
No backtest, paper-start or Freqtrade installation command has passed yet.

Source acquisition succeeded:

```bash
git clone --depth 1 --branch 2026.8 https://github.com/freqtrade/freqtrade.git .deps/freqtrade
```

The checked-out commit is 9f10e357a93c1dcf10c2a2b367659214d89c073e.
