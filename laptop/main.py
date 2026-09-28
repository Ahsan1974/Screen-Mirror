"""Start the laptop app. Run this file: python laptop/main.py"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def setup_logging() -> None:
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "phone_remote.log", encoding="utf-8"),
        ],
        force=True,
    )


def main() -> None:
    if sys.version_info < (3, 11):
        sys.stderr.write("Python 3.11 or newer is required.\n")
        sys.exit(1)
    setup_logging()
    try:
        from laptop.config.settings import ROOT as PROJECT_ROOT
        from laptop.config.settings import load_config
        from laptop.network.pairing import PairedStore
        from laptop.ui.main_window import run_app
    except ImportError as exc:
        sys.stderr.write(
            "Could not import the app dependencies.\n"
            "Create a virtual environment and run: pip install -r requirements.txt\n"
            f"Details: {exc}\n"
        )
        sys.exit(1)
    config = load_config()
    store = PairedStore(PROJECT_ROOT / "data" / "paired_devices.json")
    downloads = PROJECT_ROOT / "downloads"
    downloads.mkdir(exist_ok=True)
    logging.getLogger(__name__).info("Phone Remote starting as %s", config.device_name)
    run_app(config, store, downloads)


if __name__ == "__main__":
    main()
