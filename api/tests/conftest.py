import json
import os
import secrets
import shutil
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.evals.score import run_pipeline
from app.findings import evaluate
from app.internal import load
from app.mailer import Mailer
from app.mock.main import create_app
from app.models import Base
from app.review import Org
from app.seed.generate import SEED, Gen, write

ENV = {k: secrets.token_urlsafe(16) for k in (
    "MOCK_GRAPH_READER_ID", "MOCK_GRAPH_READER_SECRET", "MOCK_GRAPH_WRITER_ID", "MOCK_GRAPH_WRITER_SECRET",
    "MOCK_GITHUB_READ_TOKEN", "MOCK_GITHUB_ADMIN_TOKEN")}


@pytest.fixture(scope="session")
def world_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("synthetic")
    write(Gen(SEED).run(), out)
    return out


@pytest.fixture(scope="session")
def truth(world_dir):
    return json.loads((world_dir / "ground_truth.json").read_text())


@pytest.fixture(scope="session")
def entra(world_dir):
    return json.loads((world_dir / "entra.json").read_text())


@pytest.fixture
def client(world_dir):
    with TestClient(create_app(world_dir, ENV)) as c:
        yield c


def graph_token(client, writer: bool = False) -> dict:
    who = "WRITER" if writer else "READER"
    r = client.post("/login/arcwell/oauth2/v2.0/token", data={
        "client_id": ENV[f"MOCK_GRAPH_{who}_ID"], "client_secret": ENV[f"MOCK_GRAPH_{who}_SECRET"],
        "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def gh_headers(admin: bool = False) -> dict:
    return {"Authorization": f"Bearer {ENV['MOCK_GITHUB_ADMIN_TOKEN' if admin else 'MOCK_GITHUB_READ_TOKEN']}"}


# ---------- 覆核流程 ----------

AS_OF = date(2026, 11, 16)
T0 = datetime(2026, 11, 16, 1, 0)


@pytest.fixture(scope="session")
def data_root(world_dir, tmp_path_factory):
    """DATA_DIR 的結構：synthetic/ 放內部系統匯出，state/snapshots/ 放一次同步的快照。"""
    root = tmp_path_factory.mktemp("data")
    shutil.copytree(world_dir, root / "synthetic")
    snap, _, _ = run_pipeline(world_dir)
    (root / "state" / "snapshots").mkdir(parents=True)
    (root / "state" / "snapshots" / "s1.json").write_text(json.dumps(snap, ensure_ascii=False))
    return root


@pytest.fixture(scope="session")
def snapshot(data_root):
    return json.loads((data_root / "state" / "snapshots" / "s1.json").read_text())


@pytest.fixture(scope="session")
def org(data_root):
    return Org(load(data_root / "synthetic"))


@pytest.fixture(scope="session")
def findings_factory(snapshot, org):
    return lambda as_of=AS_OF: evaluate(snapshot, org.internal, as_of)


@pytest.fixture
def db_url(tmp_path):
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def db(db_url):
    eng = create_engine(db_url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with sessionmaker(eng, expire_on_commit=False)() as s:
        yield s
    eng.dispose()


@pytest.fixture
def mailer():
    return Mailer(None, 0, "keyward@arcwell.example", ".example", "http://localhost:3500")
