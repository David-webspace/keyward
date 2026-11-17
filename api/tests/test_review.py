"""覆核流程：分派、決定、例外、提醒與升級、交付執行。"""

from collections import Counter
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.execute import Ledger
from app.mailer import Mailer
from app.mock.main import create_app
from app.models import Event, Mail, ReviewException, ReviewItem
from app.review import ReviewError, create_campaign, decide, hand_off, tick, visible_item
from tests.conftest import ENV
from tests.conftest import AS_OF, T0
from tests.test_execute import Env


@pytest.fixture
def campaign(db, org, snapshot, findings_factory, mailer):
    admin = org.security
    return create_campaign(db, "2026 Q4 權限覆核", snapshot, "s1.json", findings_factory(), org, mailer, AS_OF, T0, admin)


def items(db, **where):
    q = select(ReviewItem)
    for k, v in where.items():
        q = q.where(getattr(ReviewItem, k) == v)
    return db.scalars(q).all()


def first(db, rule):
    return items(db, rule=rule)[0]


def test_routing(db, campaign, org):
    all_items = items(db)
    assert Counter(i.rule for i in all_items) == {
        "transfer_residual": 30, "inactive_account": 20, "resource_access": 18, "guest_access": 15, "excess_admin": 5,
        "peer_outlier": 15, "sod_conflict": 12, "unlinked_github": 13, "github_no_2fa": 7, "guest_github": 2}
    assert len(campaign.direct) == 25  # 離職的 19 + 6 不需覆核
    for i in all_items:
        assert i.reviewer_id != i.subject_id
        assert org.active(i.reviewer_id)
        if i.rule in ("transfer_residual", "inactive_account", "peer_outlier"):
            assert i.reviewer_id == org.ident.by_id[i.subject_id]["manager_id"]
        if i.rule in ("excess_admin", "unlinked_github", "github_no_2fa"):
            assert i.reviewer_id == org.security
    for i in items(db, rule="guest_access"):
        reason = i.finding["evidence"]["reason"]
        reg = i.finding["evidence"]["register"]
        if reason == "unregistered":
            assert i.reviewer_id == org.security
        elif reason == "sponsor_left":
            assert i.reviewer_id == org.manager_of(reg["sponsor_employee_id"])
        else:
            assert i.reviewer_id == reg["sponsor_employee_id"]


def test_one_digest_mail_per_reviewer(db, campaign):
    mails = db.scalars(select(Mail).where(Mail.kind == "assigned")).all()
    reviewers = {i.reviewer_id for i in items(db)}
    assert len(mails) == len(reviewers)
    assert sum(len(m.item_ids) for m in mails) == len(items(db))


def test_explanations_are_concrete(db, campaign):
    it = first(db, "transfer_residual")
    assert it.object in it.explanation and "轉調" in it.explanation
    launch = next(i for i in items(db, rule="resource_access") if i.object == "TMP-CBI-Launch")
    assert "RES-RD-Designs（研發設計圖檔）" in launch.explanation


def test_only_assigned_reviewer_can_see_or_decide(db, campaign, org):
    it = first(db, "transfer_residual")
    stranger = next(e for e in org.people if e not in (it.reviewer_id, *org.admins))
    with pytest.raises(ReviewError) as e:
        visible_item(db, it.id, stranger, org)
    assert e.value.status == 404
    assert visible_item(db, it.id, org.security, org).id == it.id  # IT 看得到
    with pytest.raises(ReviewError) as e:
        decide(db, it.id, org.security, org, T0, "revoke")  # 但不能代替主管決定
    assert e.value.status == 404


def test_keep_requires_reason_and_bounded_expiry(db, campaign, org):
    it = first(db, "inactive_account")
    for kwargs in ({"reason": "ok"}, {"reason": "長期出差，仍需帳號", "keep_until": AS_OF + timedelta(days=400)}):
        with pytest.raises(ReviewError) as e:
            decide(db, it.id, it.reviewer_id, org, T0, "keep", **kwargs)
        assert e.value.status == 422
    guest = first(db, "guest_access")
    with pytest.raises(ReviewError) as e:
        decide(db, guest.id, guest.reviewer_id, org, T0, "keep", "專案延長到明年")
    assert "到期日" in str(e.value)
    decide(db, it.id, it.reviewer_id, org, T0, "keep", "長期出差，仍需帳號")
    exc = db.scalar(select(ReviewException).where(ReviewException.item_id == it.id))
    assert exc.expires_on == AS_OF + timedelta(days=180)
    with pytest.raises(ReviewError) as e:
        decide(db, it.id, it.reviewer_id, org, T0, "revoke")
    assert e.value.status == 409


def test_peer_outlier_per_group(db, campaign, org):
    it = first(db, "peer_outlier")
    groups = it.finding["evidence"]["groups"]
    with pytest.raises(ReviewError):
        decide(db, it.id, it.reviewer_id, org, T0, None, groups={groups[0]: "keep"})
    choice = {g: "keep" if i == 0 else "revoke" for i, g in enumerate(groups)}
    decided = decide(db, it.id, it.reviewer_id, org, T0, None, "跨部門支援專案中", groups=choice)
    assert decided.decision == "partial"
    kept = db.scalars(select(ReviewException).where(ReviewException.item_id == it.id)).all()
    assert [k.object for k in kept] == [groups[0]]


def test_kept_items_are_suppressed_until_expiry(db, campaign, org, snapshot, findings_factory, mailer):
    it = first(db, "inactive_account")
    decide(db, it.id, it.reviewer_id, org, T0, "keep", "長期出差，仍需帳號", AS_OF + timedelta(days=30))
    nxt = create_campaign(db, "下一輪", snapshot, "s1.json", findings_factory(AS_OF + timedelta(days=7)), org, mailer,
                          AS_OF + timedelta(days=7), T0 + timedelta(days=7), org.security)
    assert nxt.suppressed == 1
    assert not items(db, campaign_id=nxt.id, account=it.account, rule="inactive_account")
    later = create_campaign(db, "到期後", snapshot, "s1.json", findings_factory(AS_OF + timedelta(days=40)), org, mailer,
                            AS_OF + timedelta(days=40), T0 + timedelta(days=40), org.security)
    assert later.suppressed == 0
    assert items(db, campaign_id=later.id, account=it.account, rule="inactive_account")


def test_reminder_then_escalation_then_overdue(db, campaign, org, mailer):
    it = first(db, "transfer_residual")
    first_reviewer = it.reviewer_id
    assert tick(db, campaign.id, org, mailer, T0 + timedelta(days=4))["reminded"] == 0
    r = tick(db, campaign.id, org, mailer, T0 + timedelta(days=5))
    assert r["reminded"] == len(items(db)) and r["escalated"] == 0
    assert tick(db, campaign.id, org, mailer, T0 + timedelta(days=5, hours=1))["reminded"] == 0  # 不重複提醒
    reminders = db.scalars(select(Mail).where(Mail.kind == "reminder")).all()
    assert len(reminders) == len({i.reviewer_id for i in items(db)})

    tick(db, campaign.id, org, mailer, T0 + timedelta(days=7))
    db.refresh(it)
    assert it.level == 1 and it.reviewer_id == org.manager_of(first_reviewer, exclude=it.subject_id)
    assert it.due_at == T0 + timedelta(days=10)

    now = T0 + timedelta(days=7)
    for _ in range(10):  # 一路升級到最上層，再逾期
        now += timedelta(days=3)
        tick(db, campaign.id, org, mailer, now)
    db.refresh(it)
    assert it.status == "overdue" and it.reviewer_id == org.security and it.decision is None  # 不會自動撤銷
    assert db.scalars(select(Event).where(Event.item_id == it.id, Event.event == "escalated")).all()


def test_hand_off_approves_manager_revocations_only(db, campaign, org, snapshot, data_root, tmp_path, world_dir, truth):
    revoked = []
    for rule in ("transfer_residual", "resource_access", "excess_admin", "guest_access", "sod_conflict"):
        it = first(db, rule)
        decide(db, it.id, it.reviewer_id, org, T0, "revoke")
        revoked.append(it)
    outlier = first(db, "peer_outlier")
    groups = outlier.finding["evidence"]["groups"]
    decide(db, outlier.id, outlier.reviewer_id, org, T0, None, "仍在支援該專案",
           groups={g: "keep" if i == 0 else "revoke" for i, g in enumerate(groups)})
    keep_one = first(db, "inactive_account")
    decide(db, keep_one.id, keep_one.reviewer_id, org, T0, "keep", "長期出差，仍需帳號")

    with pytest.raises(ReviewError) as e:
        hand_off(db, campaign.id, next(p for p in org.people if p not in org.admins), org, snapshot, tmp_path, T0)
    assert e.value.status == 403
    ledger = hand_off(db, campaign.id, org.security, org, snapshot, tmp_path, T0)
    approved = [a for a in ledger.actions.values() if a.status == "approved"]
    by_fix = Counter(a.fix for a in approved)
    assert by_fix == {"remove_group_member": 2 + len(groups) - 1, "remove_role_assignment": 1, "remove_guest": 1}
    assert all(a.approval["via"] == "review" for a in approved)
    planned = Counter(a.fix for a in ledger.actions.values() if a.status == "planned")
    assert planned == {"disable_account": 19, "remove_github_member": 6}  # 已離職：等 IT 核准
    assert [m["fix"] for m in ledger.meta["manual"]] == ["remove_erp_role"]
    with pytest.raises(ReviewError) as e:
        hand_off(db, campaign.id, org.security, org, snapshot, tmp_path, T0)
    assert e.value.status == 409

    # 交付後由執行引擎跑：主管核准的動作直接執行並驗證
    with TestClient(create_app(world_dir, ENV)) as http:
        env = Env(http, world_dir, tmp_path, truth)
        result = env.executor(Ledger(ledger.path)).run()
    assert result["verified"] == len(approved)


def test_mail_to_real_domain_is_refused():
    m = Mailer(None, 0, "keyward@arcwell.example", ".example", "")
    with pytest.raises(ValueError):
        m.send("someone@gmail.com", "x", "y")
    m.send("someone@arcwell.example", "x", "y")
