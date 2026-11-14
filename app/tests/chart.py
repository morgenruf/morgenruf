"""Where the Helm chart is, for tests that read it.

The chart lives in morgenruf/helm-charts. CI checks that repo out and sets
MORGENRUF_CHART_DIR. Locally the default is a sibling checkout, helm-charts
next to this repo. Without one the chart tests skip, except in CI, where a
missing chart fails them.
"""

from __future__ import annotations

import os
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = pathlib.Path(os.environ.get("MORGENRUF_CHART_DIR") or _REPO.parent / "helm-charts" / "morgenruf")

requires_chart = pytest.mark.skipif(
    not (CHART / "Chart.yaml").exists() and not os.environ.get("CI"),
    reason=f"no helm-charts checkout at {CHART}, set MORGENRUF_CHART_DIR",
)
