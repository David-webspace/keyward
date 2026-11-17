"""AI 規則提案的評測：群組標註與一句話寫規則。

python -m app.evals.ai_eval [--only groups|sentences] [--limit N]   # 用 LLM_* 設定的模型，輸出 eval/AI_REPORT.md
"""

import argparse
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path

from app.ai import draft_rule, label_group
from app.config import get_settings
from app.findings import POLICY, evaluate
from app.identity import Directory
from app.internal import load
from app.llm import make_llm, not_configured
from app.proposals import vocab_for
from app.rules import audience

ROOT = Path(__file__).resolve().parents[2]


def sentence_cases(groups: list[str]) -> list[dict]:
    def g(suffix: str) -> str:
        return next(x for x in groups if x.endswith(suffix))

    res = lambda text, group, depts, sites=(): {"text": text, "want": {"action": "resource", "group": group,  # noqa: E731
                                                                      "departments": sorted(depts), "sites": sorted(sites)}}
    sod = lambda text, a, b: {"text": text, "want": {"action": "sod", "pair": sorted([a, b])}}  # noqa: E731
    setting = lambda text, k, v: {"text": text, "want": {"action": "setting", "key": k, "value": v}}  # noqa: E731
    clarify = lambda text: {"text": text, "want": {"action": "clarify"}}  # noqa: E731
    return [
        res("薪資資料只有台北的人資和財務能看", "RES-Payroll", ["HR", "FIN"], ["TPE"]),
        res("董事會資料只限經營管理部門存取", "RES-Board-Materials", ["EXEC"]),
        res("人事檔案只有人資可以看", "RES-HR-Records", ["HR"]),
        res("供應商合約只開放給供應鏈、法務和財務", "RES-Supplier-Contracts", ["SC", "LEGAL", "FIN"]),
        res("2027 年預算專案只有財務和經營管理可以參與", g("-Budget-2027"), ["FIN", "EXEC"]),
        res("移轉訂價專案限財務部", g("-Transfer-Pricing"), ["FIN"]),
        res("2027 定價檢討專案只限業務和財務", g("-Pricing-Review-2027"), ["SALES", "FIN"]),
        res("2026 人才盤點專案只有人資和經營管理能看", g("-Talent-Review-2026"), ["HR", "EXEC"]),
        res("出口管制審查專案只限法務", g("-Export-Control-Review"), ["LEGAL"]),
        res("IT 管理入口只能給資訊部", "APP-Admin-Portal", ["IT"]),
        res("財務 Power BI 報表只有財務能看", "APP-PowerBI-Finance", ["FIN"]),
        res("桃園廠的 MES 只開放給桃園廠的製造和品保", "APP-MES-TYN", ["MFG", "QA"], ["TYN"]),
        sod("同一個人不能同時建立銷售訂單又開立銷貨折讓", "SO_CREATE", "CREDIT_MEMO"),
        sod("開工單的人不能自己做生產報工", "PROD_ORDER", "PROD_CONFIRM"),
        sod("負責收貨的人不可以同時做庫存調整", "GR_POST", "INV_ADJUST"),
        sod("維護料號主檔和維護 BOM 不能是同一個人", "MAT_MAINT", "BOM_MAINT"),
        sod("總帳過帳和月結關帳要由不同人負責", "GL_POST", "GL_CLOSE"),
        sod("品質凍結和品質放行不能由同一人執行", "QC_BLOCK", "QC_RELEASE"),
        sod("能維護價格的人不准核准銷售訂單", "PRICE_MAINT", "SO_APPROVE"),
        setting("超過 60 天沒登入就算殭屍帳號", "inactivity_days", 60),
        setting("新帳號給 14 天的寬限期", "new_account_grace_days", 14),
        setting("轉調後舊權限最多保留 15 天", "transfer_grace_days", 15),
        setting("閒置帳號的標準改成 120 天", "inactivity_days", 120),
        setting("45 天未登入即視為長期未登入", "inactivity_days", 45),
        clarify("那個專案的資料要管嚴一點"),
        clarify("薪水相關的東西要限制"),
        clarify("客戶資料只有業務能看"),
        clarify("限制 Slack 頻道的存取"),
        clarify("每個人的密碼要 90 天換一次"),
        clarify("研發專案只有研發可以看"),
    ]


def normalize(kind: str, proposal: dict) -> dict:
    if kind == "resource":
        return {"action": "resource", "group": proposal.get("group"), "departments": sorted(proposal.get("departments") or []),
                "sites": sorted(proposal.get("sites") or [])}
    if kind == "sod":
        return {"action": "sod", "pair": sorted([proposal.get("left"), proposal.get("right")])}
    if kind == "setting":
        return {"action": "setting", "key": proposal.get("key"), "value": proposal.get("value")}
    return {"action": "clarify"}


def run_sentences(llm, vocab, limit: int | None) -> dict:
    cases = sentence_cases(sorted(vocab.groups))[:limit]
    rows = []
    for c in cases:
        d = draft_rule(llm, c["text"], vocab)
        got = normalize(d.kind, d.proposal)
        rows.append({"text": c["text"], "want": c["want"], "got": got, "errors": d.errors, "ms": d.elapsed_ms,
                     "correct": got == c["want"] and not d.errors, **d.usage})
    by = Counter()
    for r in rows:
        by[(r["want"]["action"], r["correct"])] += 1
    return {"rows": rows, "total": len(rows), "correct": sum(r["correct"] for r in rows),
            "by_action": {a: {"total": by[(a, True)] + by[(a, False)], "correct": by[(a, True)]}
                          for a in ("resource", "sod", "setting", "clarify")},
            "guessed_instead_of_asking": sum(r["want"]["action"] == "clarify" and r["got"]["action"] != "clarify" for r in rows)}


def run_groups(llm, snapshot, internal, truth, limit: int | None) -> dict:
    ident, vocab = Directory(internal), vocab_for(snapshot, internal)
    names = sorted(truth["groups"])[:limit]
    rows = []
    for n in names:
        d = label_group(llm, n, snapshot, ident, vocab)
        t = truth["groups"][n]
        rows.append({"group": n, "want": t, "got": {k: d.proposal.get(k) for k in ("sensitivity", "owner_dept", "audience")},
                     "errors": d.errors, "rationale": d.rationale, "ms": d.elapsed_ms, **d.usage})
    valid = [r for r in rows if not r["errors"]]
    restricted = [r for r in rows if r["want"]["sensitivity"] == "restricted"]
    # 把所有通過驗證的限制級建議套上去，看隱藏問題抓不抓得到、會多出多少其他發現
    policy = json.loads(json.dumps(POLICY))
    for r in valid:
        if r["got"]["sensitivity"] == "restricted":
            policy["resources"][r["group"]] = audience(r["got"]["audience"])
    as_of = date.fromisoformat(truth["as_of"])
    base = {(f.rule, f.account, f.object) for f in evaluate(snapshot, internal, as_of)}
    after = {(f.rule, f.account, f.object) for f in evaluate(snapshot, internal, as_of, policy)}
    hidden = {("guest_resource", h["account"], h["object"]) for h in truth["hidden_issues"]}
    return {
        "rows": rows, "total": len(rows), "invalid": len(rows) - len(valid),
        "owner_correct": sum(r["got"]["owner_dept"] == r["want"]["owner_dept"] for r in rows),
        "sensitivity_correct": sum(r["got"]["sensitivity"] == r["want"]["sensitivity"] for r in rows),
        "restricted_total": len(restricted),
        "restricted_found": sum(r["got"]["sensitivity"] == "restricted" and not r["errors"] for r in restricted),
        "restricted_missed": [r["group"] for r in restricted if r["got"]["sensitivity"] != "restricted"],
        "over_restricted": [r["group"] for r in rows if r["want"]["sensitivity"] != "restricted"
                            and r["got"]["sensitivity"] == "restricted"],
        "hidden_found": len(hidden & after), "hidden_total": len(hidden), "new_findings": len(after - base),
    }


def report(model: str, g: dict | None, s: dict | None) -> str:
    lines = [f"# AI 規則提案評測（{model}）", "", "模型只產生提案；所有提案都經程式驗證，並由 IT 核准後才生效。", ""]
    if g:
        avg = sum(r["ms"] for r in g["rows"]) / max(1, g["total"]) / 1000
        lines += ["## 群組標註", "",
                  f"- 群組數：{g['total']}；未通過驗證（代碼錯誤或引用了輸入裡沒有的依據）：{g['invalid']}",
                  f"- 擁有部門正確：{g['owner_correct']} / {g['total']}",
                  f"- 敏感度正確：{g['sensitivity_correct']} / {g['total']}",
                  f"- 限制級群組：標出 {g['restricted_found']} / {g['restricted_total']}；"
                  f"**漏標（最危險）：{', '.join(g['restricted_missed']) or '無'}**",
                  f"- 把非限制級標成限制級（會多出需要覆核的項目）：{', '.join(g['over_restricted']) or '無'}",
                  f"- 套用所有限制級建議後：隱藏問題抓到 {g['hidden_found']} / {g['hidden_total']}，另外多出 {g['new_findings']} 筆發現",
                  f"- 平均每個群組 {avg:.1f} 秒", "",
                  "| 群組 | 應為 | 模型 | 驗證 |", "|---|---|---|---|"]
        for r in g["rows"]:
            ok = "✓" if r["got"]["sensitivity"] == r["want"]["sensitivity"] and r["got"]["owner_dept"] == r["want"]["owner_dept"] else "✗"
            lines.append(f"| {r['group']} | {r['want']['sensitivity']} / {r['want']['owner_dept']} | "
                         f"{r['got']['sensitivity']} / {r['got']['owner_dept']} {ok} | {'；'.join(r['errors'])[:80] or '通過'} |")
        lines.append("")
    if s:
        avg = sum(r["ms"] for r in s["rows"]) / max(1, s["total"]) / 1000
        lines += ["## 一句話寫規則", "", f"- 完全正確：{s['correct']} / {s['total']}（平均 {avg:.1f} 秒）",
                  f"- 該反問卻自己猜：{s['guessed_instead_of_asking']}", "",
                  "| 類型 | 句數 | 正確 |", "|---|---:|---:|"]
        lines += [f"| {a} | {v['total']} | {v['correct']} |" for a, v in s["by_action"].items()]
        lines += ["", "| 句子 | 結果 | 模型轉出 |", "|---|---|---|"]
        for r in s["rows"]:
            lines.append(f"| {r['text']} | {'✓' if r['correct'] else '✗'} | "
                         f"{json.dumps(r['got'], ensure_ascii=False)[:110]}{('；' + '；'.join(r['errors']))[:60] if r['errors'] else ''} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["groups", "sentences"])
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    s = get_settings()
    if msg := not_configured(s):
        raise SystemExit(msg)
    llm = make_llm(s)
    data = s.data_dir / "synthetic"
    snapshot = json.loads(max((s.data_dir / "state" / "snapshots").glob("*.json")).read_text())
    internal, truth = load(data), json.loads((data / "ground_truth.json").read_text())
    start = time.monotonic()
    g = run_groups(llm, snapshot, internal, truth, args.limit) if args.only != "sentences" else None
    st = run_sentences(llm, vocab_for(snapshot, internal), args.limit) if args.only != "groups" else None
    out = ROOT / "eval"
    out.mkdir(exist_ok=True)
    slug = s.llm_model.replace(":", "_").replace("/", "_")
    (out / f"ai-{slug}.json").write_text(json.dumps({"groups": g, "sentences": st}, ensure_ascii=False, indent=1, default=str))
    (out / f"AI_REPORT-{slug}.md").write_text(report(s.llm_model, g, st))
    print(json.dumps({"minutes": round((time.monotonic() - start) / 60, 1),
                      "groups": g and {k: g[k] for k in ("total", "invalid", "owner_correct", "sensitivity_correct",
                                                          "restricted_found", "restricted_missed", "hidden_found")},
                      "sentences": st and {k: st[k] for k in ("total", "correct", "guessed_instead_of_asking")}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
