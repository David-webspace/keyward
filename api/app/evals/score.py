"""拿發現結果對照產生器埋入的標準答案。

比對單位是「要做的動作」：(帳號, 修正動作, 物件)。分類名稱不同但動作相同（例如 GitHub 帳號
對不回 HR，被歸成孤兒而不是離職）仍算找到，另外列為分類不一致。

python -m app.evals.score          # 用 TestClient 跑 mock → 同步 → 發現 → 評分，輸出 eval/REPORT.md
"""

import json
import secrets
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.connectors.github import GitHubClient
from app.connectors.graph import GraphApp, GraphClient
from app.findings import Finding, evaluate
from app.internal import load
from app.mock.main import create_app
from app.seed.generate import Gen, write
from app.sync import empty_state, sync

ROOT = Path(__file__).resolve().parents[2]

# 標準答案的類型 → 發現規則的名稱（同一件事，名字不同）
TYPE_TO_RULE = {"launch_overprovisioned": "resource_access", "guest_access": "guest_access"}


def key(account: str, fix: str, obj: str | None) -> tuple:
    return (account, fix, obj or "")


def truth_key(i: dict) -> tuple:
    obj = i.get("group") or i.get("role") if i["fix"] in ("remove_group_member", "remove_role_assignment") else \
        i.get("rule") if i["fix"] == "remove_erp_role" else ""
    if i["type"] == "sod_conflict":
        obj = i["rule"]
    return key(i["account"], i["fix"], obj)


def score(findings: list[Finding], truth: dict) -> dict:
    want = {truth_key(i): i for i in truth["issues"]}
    got = {key(f.account, f.fix, f.object): f for f in findings}
    distractors = {d["account"] for d in truth["distractors"]}
    per_type = defaultdict(lambda: {"expected": 0, "found": 0, "missed": []})
    mismatched = []
    for k, i in want.items():
        t = per_type[i["type"]]
        t["expected"] += 1
        if k in got:
            t["found"] += 1
            rule = got[k].rule
            if rule != TYPE_TO_RULE.get(i["type"], i["type"]):
                mismatched.append({"account": i["account"], "truth": i["type"], "found_as": rule})
        else:
            t["missed"].append(i["account"])
    extra = [asdict(f) for k, f in got.items() if k not in want]
    outlier_overlap = []
    for i in truth["issues"]:
        if i["type"] == "peer_outlier" and truth_key(i) in got:
            found = set(got[truth_key(i)].evidence["groups"])
            outlier_overlap.append(len(found & set(i["groups"])) / len(i["groups"]))
    return {
        "expected": len(want), "found": sum(k in got for k in want), "false_positives": len(extra),
        "distractor_hits": sorted({f["account"] for f in extra if f["account"] in distractors}),
        "per_type": dict(per_type), "type_mismatches": mismatched, "extra": extra,
        "unconfirmed_identity": sum(1 for f in findings if not f.confirmed),
        "peer_outlier_group_recall": round(sum(outlier_overlap) / len(outlier_overlap), 3) if outlier_overlap else None,
    }


def run_pipeline(data_dir: Path, faults: dict | None = None) -> tuple[dict, list[Finding], dict]:
    env = {k: secrets.token_urlsafe(16) for k in ("MOCK_GRAPH_READER_ID", "MOCK_GRAPH_READER_SECRET",
                                                  "MOCK_GRAPH_WRITER_ID", "MOCK_GRAPH_WRITER_SECRET",
                                                  "MOCK_GITHUB_READ_TOKEN", "MOCK_GITHUB_ADMIN_TOKEN")}
    with TestClient(create_app(data_dir, env)) as http:
        if faults:
            http.put("/_mock/faults", json=faults)
        graph = GraphClient(http, GraphApp("arcwell", env["MOCK_GRAPH_READER_ID"], env["MOCK_GRAPH_READER_SECRET"]),
                            "http://testserver", "http://testserver/login", sleep=lambda _: None)
        github = GitHubClient(http, "http://testserver/github", "arcwell-demo", env["MOCK_GITHUB_READ_TOKEN"],
                              sleep=lambda _: None)
        snap = sync(graph, github, empty_state())
    truth = json.loads((data_dir / "ground_truth.json").read_text())
    findings = evaluate(snap, load(data_dir), date.fromisoformat(truth["as_of"]))
    return snap, findings, score(findings, truth)


HOLDOUT_SEEDS = range(11, 21)  # 調同儕離群門檻時沒用過的種子


def holdout() -> list[dict]:
    """換種子重新產生整份資料再跑；奇數種子同時開啟限流。"""
    rows = []
    for seed in HOLDOUT_SEEDS:
        with tempfile.TemporaryDirectory() as d:
            write(Gen(seed).run(), Path(d))
            faults = {"throttle_every": 5, "retry_after": 1} if seed % 2 else None
            snap, _, r = run_pipeline(Path(d), faults)
        rows.append({"seed": seed, "expected": r["expected"], "found": r["found"], "fp": r["false_positives"],
                     "retries": snap["stats"]["graph_retries"] + snap["stats"]["github_retries"]})
    return rows


def report(result: dict, findings: list[Finding], seeds: list[dict]) -> str:
    lines = ["# 發現規則評測", "",
             "資料：固定種子的擬真資料（`python -m app.seed.generate`）。流程：mock → 同步 → 發現規則 → 對照標準答案。",
             "比對單位是「要做的動作」（帳號、修正動作、物件）。", "",
             f"- 標準答案：**{result['expected']}** 筆，找到 **{result['found']}** 筆",
             f"- 多報（標準答案沒有的）：**{result['false_positives']}** 筆；其中命中干擾項 **{len(result['distractor_hits'])}** 筆",
             f"- 身分只是候選對應、處理前需人工確認：{result['unconfirmed_identity']} 筆",
             f"- 同儕離群：找到的群組涵蓋埋入群組的比例 {result['peer_outlier_group_recall']}", "",
             "| 類型 | 應有 | 找到 | 漏掉 |", "|---|---:|---:|---|"]
    for t, v in sorted(result["per_type"].items()):
        lines.append(f"| {t} | {v['expected']} | {v['found']} | {', '.join(v['missed']) or '—'} |")
    if result["type_mismatches"]:
        lines += ["", "## 動作正確但分類不同", "", "| 帳號 | 標準答案 | 規則判為 |", "|---|---|---|"]
        lines += [f"| {m['account']} | {m['truth']} | {m['found_as']} |" for m in result["type_mismatches"]]
    if result["extra"]:
        lines += ["", "## 多報", "", "| 規則 | 帳號 | 物件 | 依據 |", "|---|---|---|---|"]
        lines += [f"| {f['rule']} | {f['account']} | {f['object']} | {json.dumps(f['evidence'], ensure_ascii=False)[:120]} |"
                  for f in result["extra"]]
    lines += ["", "## 各規則發現數", "", "| 規則 | 筆數 |", "|---|---:|"]
    lines += [f"| {r} | {n} |" for r, n in sorted(Counter(f.rule for f in findings).items())]
    lines += ["", "## 換種子驗證", "",
              "同儕離群的門檻（持有比例 < 10%、至少 3 個罕見群組）是在種子 1–10 與預設種子上調的；",
              "下面是沒參與調參的種子，奇數種子同時開啟 mock 限流（每 5 個請求一次 429）。", "",
              "| 種子 | 應有 | 找到 | 多報 | 重試次數 |", "|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['seed']} | {r['expected']} | {r['found']} | {r['fp']} | {r['retries']} |" for r in seeds]
    lines += ["", "## 限制", "",
              "- 資料與規則出自同一個設計者。滿分代表規則確實照 policy.yaml 執行、同步與身分對應沒有遺漏，"
              "不代表在真實公司也能全對：真實資料會有規則沒想到的例外。",
              "- 同儕離群是統計判斷，同一組同事裡有多個離群者時會互相稀釋；門檻調高會漏抓、調低會多報（調參紀錄見種子 1–10 的結果）。",
              "- GitHub 帳號對不上登記表時一律只建議「確認身分」，不建議直接移除。"]
    return "\n".join(lines) + "\n"


def main():
    data_dir = Path(ROOT.parent / "data" / "synthetic")
    _, findings, result = run_pipeline(data_dir)
    out = ROOT / "eval"
    out.mkdir(exist_ok=True)
    seeds = holdout()
    (out / "REPORT.md").write_text(report(result, findings, seeds))
    print(json.dumps({k: result[k] for k in ("expected", "found", "false_positives", "distractor_hits",
                                             "type_mismatches", "unconfirmed_identity", "peer_outlier_group_recall")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
