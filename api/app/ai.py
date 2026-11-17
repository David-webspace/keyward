"""兩個 AI 功能，都只產生「規則變更提案」，不會直接生效：

1. 群組標註：讀群組名稱、說明、成員的部門與據點分布，建議敏感度、擁有部門、可存取對象
2. 一句話寫規則：把 IT 主管的一句話轉成資源存取、職責分離或門檻規則；意思不清楚就反問

模型的輸出一律經程式驗證：代碼必須真的存在、引用的依據必須逐字出現在輸入裡（防止模型捏造理由）。
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.identity import Directory
from app.llm import LLM
from app.rules import SETTINGS, Vocabulary, validate

ORG_GROUP = re.compile(r"^SG-[A-Z]{3}-")

TX_ZH = {
    "VENDOR_MAINT": "維護供應商主檔", "PAY_APPROVE": "核准付款", "PO_CREATE": "建立採購單", "GR_POST": "收貨過帳",
    "PO_APPROVE": "核准採購單", "AP_INVOICE": "登錄應付發票", "PAY_RUN": "執行付款", "CUST_MAINT": "維護客戶主檔",
    "CREDIT_MEMO": "開立銷貨折讓", "GI_POST": "出貨過帳", "INV_ADJUST": "庫存調整", "INV_COUNT": "盤點",
    "SO_CREATE": "建立銷售訂單", "SO_APPROVE": "核准銷售訂單", "PRICE_MAINT": "維護價格", "USER_ADMIN": "ERP 帳號管理",
    "AR_INVOICE": "開立應收發票", "GL_POST": "總帳過帳", "GL_CLOSE": "月結關帳", "COST_RUN": "成本計算",
    "ASSET_MAINT": "固定資產維護", "MAT_MAINT": "料號主檔維護", "QC_BLOCK": "品質凍結", "QC_RELEASE": "品質放行",
    "PROD_ORDER": "開立工單", "PROD_CONFIRM": "生產報工", "BOM_MAINT": "BOM 維護", "REPORT_FIN": "財務報表",
    "REPORT_OPS": "營運報表",
}


@dataclass
class Draft:
    kind: str                     # group_label / resource / sod / setting / clarify
    proposal: dict
    rationale: str | None
    evidence: list[str]
    errors: list[str]
    model: str
    elapsed_ms: int
    usage: dict = field(default_factory=dict)


def _norm(s: str) -> str:
    return "".join(s.split())


_SPLIT = re.compile(r"[\s：:，,、；;（）()「」]+")


def _evidence_errors(evidence: list[str], source: str) -> list[str]:
    """每一段引用都必須逐字出現在輸入裡。允許把幾段原文拼在一起引用（例如名稱加說明），所以逐段檢查。"""
    if not evidence:
        return ["沒有引用任何依據"]
    src = _norm(source)
    bad = [e for e in evidence if any(len(part) >= 2 and _norm(part) not in src for part in _SPLIT.split(e))
           or not any(len(part) >= 2 for part in _SPLIT.split(e))]
    return [f"引用的依據「{e}」沒有出現在輸入中" for e in bad]


def _as_list(value) -> list[str]:
    """有些模型會把清單整個當成一段 JSON 文字回傳，這裡統一還原成字串清單。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(value, str):
            return [value]
    return [v for v in value or [] if isinstance(v, str)]


def _codes(vocab: Vocabulary, attr: str) -> str:
    return "、".join(f"{k} {v}" for k, v in getattr(vocab, attr).items())


# ---------- 群組標註 ----------

LABEL_SYSTEM = """你是 Arcwell Electronics IT 資安團隊的助理，替沒有標註的 Entra ID 群組建議敏感度、擁有部門與可存取對象。
你的建議會經過程式驗證，最後由 IT 主管核准，不會直接生效。

敏感度定義：
- restricted：資料外流會造成財務、法律、個資或商業機密損害。例如預算、薪資、人事考核、合約、定價與報價、稽核、出口管制、系統管理權限。
- internal：公司內部工作使用，員工依工作需要存取。例如一般專案、系統登入、教育訓練、設備管理、外部合作夥伴協作。
- general：沒有敏感資料的一般用途。例如社團、印表機、全公司公告、訪客、測試或已停用的群組。

擁有部門：最可能負責管理這個群組的部門，從部門清單選一個代碼。
可存取對象：只有 restricted 需要填。列出應該可以存取的部門代碼，必須包含擁有部門；只限特定據點時才填據點代碼，否則留空。
依據：從群組資料中逐字複製 1 到 3 段支持判斷的文字（例如群組名稱裡的關鍵字、說明、成員部門分布那一行），不可改寫。

部門清單：{depts}
據點清單：{sites}"""


def group_context(name: str, snapshot: dict, ident: Directory) -> str:
    entra = snapshot["entra"]
    by_name = {g["displayName"]: g for g in entra["groups"]}
    gname = {g["id"]: g["displayName"] for g in entra["groups"]}
    users = {u["id"]: u for u in entra["users"]}
    parents = defaultdict(list)
    for gid, ms in entra["members"].items():
        for m in ms:
            if m["type"] == "group":
                parents[m["id"]].append(gname[gid])
    g = by_name[name]
    direct = entra["members"].get(g["id"], [])
    stack, seen, people = [g["id"]], set(), set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for m in entra["members"].get(cur, []):
            (people.add if m["type"] == "user" else stack.append)(m["id"])
    depts, sites, guests = Counter(), Counter(), Counter()
    for uid in people:
        u = users.get(uid)
        if not u:
            continue
        m = ident.entra(u)
        if m.kind == "employee":
            depts[m.record["dept"]] += 1
            sites[m.record["site"]] += 1
        elif m.kind == "guest":
            guests[(u.get("mail") or "").split("@")[-1]] += 1
    fmt = lambda c: "、".join(f"{k} {v}" for k, v in c.most_common()) or "無"  # noqa: E731
    subgroups = [gname[m["id"]] for m in direct if m["type"] == "group"]
    return "\n".join([
        f"群組名稱：{name}",
        f"說明：{g.get('description') or '（沒有說明）'}",
        f"成員人數（含子群組）：{len(people)}",
        f"成員部門分布：{fmt(depts)}",
        f"成員據點分布：{fmt(sites)}",
        f"外部來賓所屬公司：{fmt(guests)}",
        f"直接包含的子群組：{'、'.join(subgroups) or '無'}",
        f"被以下群組包含：{'、'.join(parents[g['id']]) or '無'}",
    ])


def label_group(llm: LLM, name: str, snapshot: dict, ident: Directory, vocab: Vocabulary) -> Draft:
    ctx = group_context(name, snapshot, ident)
    schema = {"type": "object", "properties": {
        "sensitivity": {"type": "string", "enum": ["restricted", "internal", "general"]},
        "owner_dept": {"type": "string", "enum": sorted(vocab.departments)},
        "audience_departments": {"type": "array", "items": {"type": "string", "enum": sorted(vocab.departments)}},
        "audience_sites": {"type": "array", "items": {"type": "string", "enum": sorted(vocab.sites)}},
        "rationale": {"type": "string", "description": "一兩句話說明判斷理由"},
        "evidence": {"type": "array", "items": {"type": "string"}, "description": "從群組資料逐字複製的依據"},
    }, "required": ["sensitivity", "owner_dept", "rationale", "evidence"]}
    system = LABEL_SYSTEM.format(depts=_codes(vocab, "departments"), sites=_codes(vocab, "sites"))
    x = llm.extract(system, ctx, "label_group", "回傳這個群組的敏感度、擁有部門與可存取對象建議", schema)
    meta = {"model": x.model, "elapsed_ms": int(x.seconds * 1000),
            "usage": {"input_tokens": x.input_tokens, "output_tokens": x.output_tokens}}
    if x.args is None:
        return Draft("group_label", {"group": name}, None, [], ["模型沒有回傳結構化結果"], **meta)
    a = x.args
    proposal = {"group": name, "sensitivity": a.get("sensitivity"), "owner_dept": a.get("owner_dept"),
                "audience": {"departments": a.get("audience_departments") or [], "sites": a.get("audience_sites") or []}}
    if proposal["sensitivity"] != "restricted":
        proposal["audience"] = {"departments": [], "sites": []}
    evidence = _as_list(a.get("evidence"))
    errors = validate("group_label", proposal, vocab) + _evidence_errors(evidence, ctx)
    return Draft("group_label", proposal, a.get("rationale"), evidence, errors, **meta)


# ---------- 一句話寫規則 ----------

RULE_SYSTEM = """你是 Arcwell Electronics IT 資安團隊的助理，把 IT 主管用一句話描述的規則，轉成結構化的規則草稿。
草稿會經過程式驗證與影響預覽，由 IT 主管核准後才生效。

支援三種規則（action）：
1. resource：某個資源（群組）只有哪些部門可以存取，必要時再限定據點。group 必須是下方群組清單中的確切名稱。
2. sod：職責分離，同一個人不能同時擁有兩種 ERP 交易權限。left、right 是交易代碼，zh 用中文簡述這條規則。
3. setting：調整門檻。key 只能是 inactivity_days（幾天沒登入算殭屍帳號）、new_account_grace_days（新帳號幾天內沒登入不算）、transfer_grace_days（轉調後幾天內還有舊權限不算）；value 是天數。

句子提到的資源在群組清單中找不到、可能對應到兩個以上的群組、意思有兩種以上的解讀、或不屬於以上三種規則時，
action 請填 clarify，並在 question 用一句話反問，不要猜。
依據：從句子中逐字複製對應的詞，不可改寫。
departments 只能填部門代碼（例如 HR、FIN），不是群組名稱；sites 只能填據點代碼。

範例（只示範格式）：
- 「品質稽核文件只限品保」→ action resource，group RES-Quality-Audit，departments [QA]，evidence ["品質稽核文件", "品保"]
- 「建立採購單和核准採購單不能是同一人」→ action sod，left PO_CREATE，right PO_APPROVE，evidence ["建立採購單", "核准採購單"]
- 「超過 100 天沒登入就算殭屍帳號」→ action setting，key inactivity_days，value 100，evidence ["100 天沒登入"]
- 「那批資料要管嚴一點」→ action clarify，question「請問是哪一個資源？要開放給哪些部門？」

部門清單：{depts}
據點清單：{sites}
ERP 交易代碼：{tx}
群組清單（名稱：說明）：
{groups}"""


def draft_rule(llm: LLM, sentence: str, vocab: Vocabulary) -> Draft:
    # 據點×部門的組織群組數量多又不是資源，不列給模型
    groups = "\n".join(f"- {g}：{d or '（沒有說明）'}" for g, d in sorted(vocab.groups.items()) if not ORG_GROUP.match(g))
    tx = sorted(vocab.transactions)
    schema = {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["resource", "sod", "setting", "clarify"]},
        "group": {"type": "string"},
        "departments": {"type": "array", "items": {"type": "string", "enum": sorted(vocab.departments)}},
        "sites": {"type": "array", "items": {"type": "string", "enum": sorted(vocab.sites)}},
        "left": {"type": "string", "enum": tx}, "right": {"type": "string", "enum": tx}, "zh": {"type": "string"},
        "key": {"type": "string", "enum": sorted(SETTINGS)}, "value": {"type": "integer"},
        "question": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}, "description": "從句子逐字複製的依據"},
    }, "required": ["action", "evidence"]}
    system = RULE_SYSTEM.format(depts=_codes(vocab, "departments"), sites=_codes(vocab, "sites"),
                                tx="、".join(f"{t} {TX_ZH.get(t, '')}" for t in tx), groups=groups)
    x = llm.extract(system, sentence, "draft_rule", "回傳規則草稿，或在需要時反問", schema)
    meta = {"model": x.model, "elapsed_ms": int(x.seconds * 1000),
            "usage": {"input_tokens": x.input_tokens, "output_tokens": x.output_tokens}}
    if x.args is None:
        return Draft("clarify", {}, None, [], ["模型沒有回傳結構化結果"], **meta)
    a = x.args
    action = a.get("action")
    evidence = _as_list(a.get("evidence"))
    if action == "clarify":
        return Draft("clarify", {"question": a.get("question") or "請再說明清楚一點"}, None, evidence, [], **meta)
    if action == "resource":
        proposal = {"group": a.get("group"), "departments": a.get("departments") or [], "sites": a.get("sites") or []}
    elif action == "sod":
        proposal = {"left": a.get("left"), "right": a.get("right"),
                    "zh": a.get("zh") or f"{TX_ZH.get(a.get('left'), '')} × {TX_ZH.get(a.get('right'), '')}"}
    elif action == "setting":
        proposal = {"key": a.get("key"), "value": a.get("value")}
    else:
        return Draft("clarify", {"question": "這句話不屬於支援的規則類型"}, None, evidence, [f"不支援的 action：{action}"], **meta)
    errors = validate(action, proposal, vocab) + _evidence_errors(evidence, sentence)
    return Draft(action, proposal, None, evidence, errors, **meta)
