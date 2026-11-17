"""AI 規則提案：用假模型固定回傳，測驗證、影響預覽、套用、撤回，以及 API 權限。"""

import pytest
from fastapi.testclient import TestClient

from app import main, proposals
from app.ai import draft_rule, group_context, label_group
from app.config import get_settings
from app.db import engine
from app.findings import evaluate
from app.llm import Extraction
from app.review import ReviewError
from app.rules import effective
from tests.conftest import AS_OF, T0


class FakeLLM:
    """依輸入內容回傳預先寫好的結果；calls 記錄被問了什麼。"""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def extract(self, system, user, tool_name, tool_description, schema):
        self.calls.append(user)
        return Extraction(self.answer(user), "fake-model", 10, 5, 0.01)


@pytest.fixture(scope="module")
def pricing(truth):
    return truth["hidden_issues"][0]["object"]


def label(sensitivity="restricted", owner="SALES", audience=("SALES",), evidence=("Pricing-Review-2027",)):
    return lambda user: {"sensitivity": sensitivity, "owner_dept": owner, "audience_departments": list(audience),
                         "rationale": "報價審查屬於商業機密", "evidence": list(evidence)}


def test_group_context_shows_member_mix(snapshot, org, pricing):
    ctx = group_context(pricing, snapshot, org.ident)
    assert f"群組名稱：{pricing}" in ctx and "SALES" in ctx
    assert "novaterm.example" in ctx or "helios-power.example" in ctx  # 埋進去的客戶來賓看得到


def test_restricted_label_reveals_hidden_guest_access(db, snapshot, org, pricing, truth):
    internal = org.internal
    vocab = proposals.vocab_for(snapshot, internal)
    draft = label_group(FakeLLM(label()), pricing, snapshot, org.ident, vocab)
    assert draft.errors == []
    p = proposals.create(db, draft, "classifier", pricing, pricing, org.security, snapshot, internal, AS_OF, T0)
    assert p.status == "proposed"
    added = {(r["rule"], r["account"], r["object"]) for r in p.impact["added_rows"]}
    hidden = {("guest_resource", h["account"], h["object"]) for h in truth["hidden_issues"]}
    assert hidden <= added

    before = {f.account for f in evaluate(snapshot, internal, AS_OF, effective(db)) if f.rule == "guest_resource"}
    proposals.decide(db, p.id, org.security, "apply", T0, snapshot, internal, AS_OF)
    after = {f.account for f in evaluate(snapshot, internal, AS_OF, effective(db)) if f.rule == "guest_resource"}
    assert not before and {h["account"] for h in truth["hidden_issues"]} <= after

    proposals.decide(db, p.id, org.security, "revert", T0, snapshot, internal, AS_OF)
    assert pricing not in effective(db)["resources"]


def test_made_up_evidence_is_rejected(db, snapshot, org, pricing):
    vocab = proposals.vocab_for(snapshot, org.internal)
    draft = label_group(FakeLLM(label(evidence=("這個群組存放董事會簡報",))), pricing, snapshot, org.ident, vocab)
    assert any("沒有出現在輸入中" in e for e in draft.errors)
    p = proposals.create(db, draft, "classifier", pricing, pricing, org.security, snapshot, org.internal, AS_OF, T0)
    assert p.status == "invalid" and p.impact is None
    with pytest.raises(ReviewError) as e:
        proposals.decide(db, p.id, org.security, "apply", T0, snapshot, org.internal, AS_OF)
    assert e.value.status == 422
    # IT 修改後可以套用：重新驗證、重新預覽
    fixed = {"sensitivity": "restricted", "owner_dept": "SALES", "audience": {"departments": ["SALES", "EXEC"], "sites": []}}
    p = proposals.decide(db, p.id, org.security, "apply", T0, snapshot, org.internal, AS_OF, fixed)
    assert p.status == "applied" and p.proposal["group"] == pricing and p.impact["added"] > 0


@pytest.mark.parametrize("answer, message", [
    (label(owner="XYZ"), "擁有部門"),
    (label(audience=("FIN",)), "必須包含擁有部門"),
    (label(audience=()), "沒有指定"),
])
def test_label_validation(snapshot, org, pricing, answer, message):
    draft = label_group(FakeLLM(answer), pricing, snapshot, org.ident, proposals.vocab_for(snapshot, org.internal))
    assert any(message in e for e in draft.errors)


def test_internal_label_has_no_effect(db, snapshot, org):
    draft = label_group(FakeLLM(label("internal", "IT", (), ("SG-Laptop-Pilot",))), "SG-Laptop-Pilot", snapshot, org.ident,
                        proposals.vocab_for(snapshot, org.internal))
    p = proposals.create(db, draft, "classifier", "SG-Laptop-Pilot", "SG-Laptop-Pilot", org.security, snapshot,
                         org.internal, AS_OF, T0)
    assert p.status == "proposed" and p.impact is None and p.proposal["audience"]["departments"] == []


def sentence(db, snapshot, org, text, answer):
    draft = draft_rule(FakeLLM(lambda _: answer), text, proposals.vocab_for(snapshot, org.internal))
    return proposals.create(db, draft, "sentence", text, "", org.security, snapshot, org.internal, AS_OF, T0)


def test_sentence_rules(db, snapshot, org):
    s = "超過 20 天沒登入就算殭屍帳號"  # 資料裡在職員工最多 25 天沒登入，門檻降到 20 天才會多出發現
    p = sentence(db, snapshot, org, s, {"action": "setting", "key": "inactivity_days", "value": 20, "evidence": ["20 天沒登入"]})
    assert p.status == "proposed" and p.impact["added"] > 0 and p.impact["removed"] == 0

    s = "同一個人不能同時建立銷售訂單又開立銷貨折讓"
    p = sentence(db, snapshot, org, s, {"action": "sod", "left": "SO_CREATE", "right": "CREDIT_MEMO",
                                        "evidence": ["建立銷售訂單", "開立銷貨折讓"]})
    assert p.status == "proposed" and p.proposal["zh"]

    s = "董事會資料只有經營管理能看"
    p = sentence(db, snapshot, org, s, {"action": "resource", "group": "RES-Board-Material", "departments": ["EXEC"],
                                        "evidence": ["董事會資料"]})
    assert p.status == "invalid" and any("找不到群組" in e for e in p.errors)

    s = "那個專案的資料要管嚴一點"
    p = sentence(db, snapshot, org, s, {"action": "clarify", "question": "請問是哪一個專案？", "evidence": []})
    assert p.status == "clarify" and p.proposal["question"]

    s = "殭屍帳號改成 3 天"
    p = sentence(db, snapshot, org, s, {"action": "setting", "key": "inactivity_days", "value": 3, "evidence": ["3 天"]})
    assert p.status == "invalid"


def test_unlabeled_groups_shrink_as_proposals_are_made(db, snapshot, org, pricing):
    before = proposals.unlabeled_groups(db, snapshot)
    assert pricing in before and "RES-Payroll" not in before and not any(g.startswith("SG-TPE-") for g in before)
    made = proposals.suggest_groups(db, FakeLLM(lambda user: label("internal", "IT", (), (user.splitlines()[0],))(user)),
                                    3, org.security, snapshot, org.internal, AS_OF, T0)
    assert len(made) == 3 and len(proposals.unlabeled_groups(db, snapshot)) == len(before) - 3


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
    main.app.dependency_overrides.clear()
    for f in (get_settings, engine, main.org):
        f.cache_clear()


def test_api_flow(api, org, pricing, truth):
    api.post("/auth/demo-login", json={"employee_id": org.security})
    assert api.post("/policy/drafts", json={"text": "超過 60 天沒登入就算殭屍帳號"}).status_code == 503  # 沒設定模型

    main.app.dependency_overrides[main.get_llm] = lambda: FakeLLM(
        lambda user: label()(user) if pricing in user else label("general", "HR", (), (user.splitlines()[0],))(user))
    pid = None
    while pid is None:  # 每次最多標註 20 個，一路標到報價審查專案為止
        r = api.post("/policy/groups/suggest", json={"limit": 20}).json()
        assert r["made"]
        pid = next((p["id"] for p in r["made"] if p["target"] == pricing), None)
    assert api.post(f"/policy/proposals/{pid}/apply", json={}).json()["status"] == "applied"
    rules = {f["account"] for f in api.get(f"/findings?as_of={AS_OF}").json()["items"] if f["rule"] == "guest_resource"}
    assert {h["account"] for h in truth["hidden_issues"]} <= rules
    assert api.post(f"/policy/proposals/{pid}/apply", json={}).status_code == 409

    api.cookies.clear()
    api.post("/auth/demo-login", json={"employee_id": next(p for p in org.people if p not in org.admins)})
    assert api.get("/policy").status_code == 403
    assert api.post(f"/policy/proposals/{pid}/revert", json={}).status_code == 403


def test_settings_require_model(monkeypatch):
    from app.config import Settings
    from app.llm import not_configured
    base = dict(database_url="sqlite://", jwt_secret="x", auth_mode="demo")
    assert "LLM_PROVIDER" in not_configured(Settings(**base))
    assert not_configured(Settings(**base, llm_provider="openai_compatible", llm_model="m", llm_base_url="http://x")) is None
    assert "LLM_API_KEY" in not_configured(Settings(**base, llm_provider="anthropic", llm_model="m"))


def test_evidence_returned_as_json_text_is_parsed(snapshot, org, pricing):
    answer = lambda user: label()(user) | {"evidence": '["Pricing-Review-2027"]'}  # noqa: E731
    draft = label_group(FakeLLM(answer), pricing, snapshot, org.ident, proposals.vocab_for(snapshot, org.internal))
    assert draft.evidence == ["Pricing-Review-2027"] and draft.errors == []
