"""Command line interface for the email transferrer."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from email_transferrer import EmailTransferrer, create_transferrer, load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transfer emails between servers based on configuration")
    parser.add_argument("--config", "-c", default="config.yaml", help="Path to the YAML configuration file")
    parser.add_argument("--once", action="store_true", help="Run a single transfer cycle and exit")
    parser.add_argument("--log-level", default=None, help="Override log level (DEBUG, INFO, WARNING, ...)")
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(Path(args.config))
    log_level = args.log_level or config.log_level
    configure_logging(log_level)

    transferrer: EmailTransferrer = create_transferrer(config)

    if args.once:
        transferrer.run_once()
    else:  # pragma: no cover - infinite loop not tested
        transferrer.run_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

