import os
import tempfile
from pathlib import Path

os.environ.setdefault("VID2GRAPH_LLM_PROVIDER", "mock")
os.environ.setdefault("VID2GRAPH_EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("VID2GRAPH_WHISPER_BACKEND", "none")
_tmp = tempfile.mkdtemp(prefix="vid2graph-test-")
os.environ["VID2GRAPH_DATA_DIR"] = _tmp

import pytest  # noqa: E402

from app.db.database import Database, set_db  # noqa: E402


@pytest.fixture()
def db() -> Database:
    d = Database(Path(_tmp) / "test.sqlite3")
    set_db(d)
    yield d
    d.close()


@pytest.fixture()
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
