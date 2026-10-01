"""Each test gets its own MongoDB databases (a unique name prefix), dropped afterwards. Needs a local mongod."""
import uuid

import pytest

from sidekick import db


@pytest.fixture(autouse=True)
def isolated_mongo(monkeypatch):
    prefix = f"rsktest_{uuid.uuid4().hex[:10]}"
    monkeypatch.setenv("RSK_DB_PREFIX", prefix)
    yield prefix
    c = db.client()
    for name in c.list_database_names():
        if name.startswith(prefix + "_"):
            c.drop_database(name)
