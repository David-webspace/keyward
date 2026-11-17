"""覆核 API：登入、權限、端到端流程，以及 migration 與資料模型一致。"""

from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import main
from app.config import get_settings
from app.db import engine
from app.models import Base
from tests.conftest import AS_OF, T0


@pytest.fixture
def api(monkeypatch, data_root, db, db_url):
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET", "test-secret-" + "x" * 32)
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("DATA_DIR", str(data_root))
    for f in (get_settings, engine, main.org):
        f.cache_clear()
    with TestClient(main.app) as c:
        yield c
    for f in (get_settings, engine, main.org):
        f.cache_clear()


def login(api, emp):
    api.cookies.clear()
    r = api.post("/auth/demo-login", json={"employee_id": emp})
    assert r.status_code == 200, r.text
    return r.json()


def test_login_rules(api, org):
    assert api.get("/me").status_code == 401
    assert api.post("/auth/demo-login", json={"employee_id": "E00000"}).status_code == 401
    left = next(e["employee_id"] for e in org.internal.hr if e["status"] == "terminated"
                and org.ident.by_email[e["email"].lower()]["status"] == "terminated")
    assert api.post("/auth/demo-login", json={"employee_id": left}).status_code == 401  # 離職者不能登入
    assert login(api, org.security)["is_admin"] is True


def test_non_admin_cannot_manage_campaigns(api, org):
    login(api, next(p for p in org.people if p not in org.admins))
    assert api.post("/campaigns", json={"name": "偷建活動"}).status_code == 403
    assert api.get("/campaigns/1").status_code == 403


def test_end_to_end(api, org):
    login(api, org.security)
    c = api.post("/campaigns", json={"name": "2026 Q4", "as_of": str(AS_OF)}).json()
    assert c["total"] == 137 and c["direct"] == 25

    # 找一位主管，看自己的待辦、做決定
    login(api, org.security)
    my = api.get("/reviews").json()
    assert my and all(i["status"] == "pending" for i in my)
    target = next(i for i in my if i["rule"] == "excess_admin")
    assert api.post(f"/reviews/{target['id']}/decision", json={"decision": "revoke"}).status_code == 200

    mgr_item = None
    for emp in org.people:
        if emp in org.admins:
            continue
        login(api, emp)
        items = api.get("/reviews").json()
        if any(i["rule"] == "transfer_residual" for i in items):
            mgr_item = next(i for i in items if i["rule"] == "transfer_residual")
            break
    assert mgr_item and mgr_item["explanation"]
    r = api.post(f"/reviews/{mgr_item['id']}/decision", json={"decision": "keep", "reason": "ok"})
    assert r.status_code == 422
    assert api.post(f"/reviews/{mgr_item['id']}/decision",
                    json={"decision": "revoke"}).json()["decision"] == "revoke"

    # 別人看不到這個項目：一律 404
    other = next(p for p in org.people if p not in org.admins and p != emp)
    login(api, other)
    assert api.get(f"/reviews/{mgr_item['id']}").status_code == 404
    assert api.post(f"/reviews/{mgr_item['id']}/decision", json={"decision": "keep"}).status_code == 404

    login(api, org.security)
    t = api.post(f"/campaigns/{c['id']}/tick", json={"now": (T0 + timedelta(days=30)).isoformat()}).json()
    assert t["escalated"] > 0
    h = api.post(f"/campaigns/{c['id']}/hand-off").json()
    assert h["approved"] == 2 and h["awaiting_it"] == 25
    assert api.get(f"/campaigns/{c['id']}").json()["status"] == "handed_off"


def test_demo_login_disabled_outside_demo(api, monkeypatch, org):
    monkeypatch.setenv("AUTH_MODE", "entra")
    get_settings.cache_clear()
    assert api.post("/auth/demo-login", json={"employee_id": org.security}).status_code == 404


def test_migration_matches_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config("alembic.ini")
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    with create_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []


def test_admin_views_and_evidence(api, org, truth):
    import io
    import zipfile

    login(api, org.security)
    c = api.post("/campaigns", json={"name": "2026 Q4", "as_of": str(AS_OF)}).json()
    assert [x["id"] for x in api.get("/campaigns").json()] == [c["id"]]
    detail = api.get(f"/campaigns/{c['id']}").json()
    assert sum(r.get("pending", 0) for r in detail["by_rule"]) == 137 and detail["waiting_on"]
    assert len(api.get(f"/campaigns/{c['id']}/items?rule=excess_admin").json()) == 5

    f = api.get(f"/findings?as_of={AS_OF}").json()
    assert len(f["items"]) == 162 and f["suppressed"] == 0

    resid = next(i for i in truth["issues"] if i["type"] == "transfer_residual")
    p = api.get(f"/people/{resid['employee_id']}?as_of={AS_OF}").json()
    groups = {g["name"] for g in p["entra"][0]["direct_groups"]}
    assert resid["group"] in groups
    assert any(x["rule"] == "transfer_residual" for x in p["findings"]) and p["transfers"]
    assert api.get("/people/E00000").status_code == 404
    assert api.get(f"/people?q={p['name']}").json()[0]["employee_id"] == p["employee_id"]

    demo = api.get("/demo/accounts").json()
    assert demo[0]["employee_id"] == org.security and demo[-1]["pending"] == 0

    r = api.get(f"/campaigns/{c['id']}/evidence")
    assert r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"summary.md", "items.csv", "events.csv", "mails.csv", "policy.yaml"} <= set(z.namelist())
    assert z.read("items.csv").decode("utf-8-sig").count("\n") == 138  # 表頭 + 137 項

    login(api, next(p for p in org.people if p not in org.admins))
    for path in ("/findings", f"/people/{resid['employee_id']}", f"/campaigns/{c['id']}/evidence", "/campaigns"):
        assert api.get(path).status_code == 403
