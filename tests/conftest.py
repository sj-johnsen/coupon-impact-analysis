from pathlib import Path

import pandas as pd
import pytest

from coupon_analysis import config as C

DATA = C.project_root() / C.DATA_FILENAME
NEEDS_DATA = {"test_pipeline.py", "test_word.py"}       # these run the whole pipeline on the course data


def pytest_collection_modifyitems(config, items):
    if DATA.exists():
        return
    skip = pytest.mark.skip(reason=f"course data not included; put {C.DATA_FILENAME} next to pyproject.toml")
    for item in items:
        if item.path.name in NEEDS_DATA:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def raw() -> pd.DataFrame:
    if not DATA.exists():
        pytest.skip(f"course data not included; put {C.DATA_FILENAME} next to pyproject.toml to run this test")
    return pd.read_csv(DATA)


@pytest.fixture()
def df(raw) -> pd.DataFrame:
    return raw.copy()
