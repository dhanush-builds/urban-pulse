import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))

from db import get_engine  # noqa: E402


@pytest.fixture(scope="session")
def raw():
    return pd.read_csv(ROOT / "data/raw/nyc311_raw.csv", dtype=str, keep_default_na=False)


@pytest.fixture(scope="session")
def clean():
    df = pd.read_csv(ROOT / "data/clean/nyc311_clean.csv", low_memory=False,
                     parse_dates=["created_date", "closed_date"])
    return df


@pytest.fixture(scope="session")
def engine():
    eng = get_engine()
    try:
        with eng.connect() as conn:
            conn.exec_driver_sql("select 1")
    except Exception:
        pytest.exit("database is not reachable: start the container and check .env")
    return eng


@pytest.fixture(scope="session")
def extraction_log():
    return json.loads((ROOT / "docs/extraction_log.json").read_text())


@pytest.fixture(scope="session")
def sql_tasks():
    """analysis.sql split into {task number: [statements]}."""
    text = (ROOT / "sql/analysis.sql").read_text()
    tasks = {}
    current = None
    for chunk in re.split(r"^-- (\d+)\. ", text, flags=re.M)[1:]:
        if chunk.isdigit():
            current = int(chunk)
            tasks[current] = []
        else:
            lines = chunk.split("\n")[1:]          # first line is the task title
            body = "\n".join(l for l in lines if not l.strip().startswith("--"))
            tasks[current] = [s.strip() for s in body.split(";") if s.strip()]
    return tasks
