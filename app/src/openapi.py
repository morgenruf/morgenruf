"""Deterministic, offline browser API contract export.

Usage: PYTHONPATH=app python -m src.openapi --output app/openapi.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def specification():
    from src.http_app import create_http_app

    app = create_http_app(schema_only=True)
    return app.extensions["morgenruf_api"].spec.to_dict()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(specification(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
