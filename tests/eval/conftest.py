from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Path resolution: tests/eval/conftest.py -> tests/ -> project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_GOLDEN_DATASET_PATH = _PROJECT_ROOT / "tests" / "fixtures" / "golden_dataset.json"


@pytest.fixture(scope="session")
def golden_dataset() -> list[dict]:
    """Load the golden dataset fixture. Session-scoped for performance."""
    if not _GOLDEN_DATASET_PATH.exists():
        pytest.fail(
            f"Golden dataset not found at {_GOLDEN_DATASET_PATH}. "
            "Ensure tests/fixtures/golden_dataset.json exists."
        )
    data = json.loads(_GOLDEN_DATASET_PATH.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="session")
def mock_llm_active() -> bool:
    """True when MOCK_LLM=1 is set in the environment."""
    return os.environ.get("MOCK_LLM") == "1"


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Absolute path to the project root directory."""
    return _PROJECT_ROOT
