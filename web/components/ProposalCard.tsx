"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { account, dept } from "@/lib/format";
import { SENSITIVITY, describe } from "@/lib/rules";
import type { Proposal } from "@/lib/types";

const DEPTS = ["EXEC", "FIN", "LEGAL", "HR", "IT", "SALES", "FAE", "RDHW", "RDFW", "TEST", "MFG", "QA", "SC", "WH"];
const STATUS: Record<string, string> = {
  proposed: "待決定", invalid: "未通過驗證", clarify: "模型反問", applied: "已生效", rejected: "已捨棄", reverted: "已撤回",
};

export function ProposalCard({ p }: { p: Proposal }) {
  const router = useRouter();
  const x = p.proposal as { sensitivity?: string; owner_dept?: string; audience?: { departments: string[]; sites: string[] } };
  const editable = p.kind === "group_label" && (p.status === "proposed" || p.status === "invalid");
  const [editing, setEditing] = useState(false);
  const [sens, setSens] = useState(x.sensitivity ?? "internal");
  const [owner, setOwner] = useState(x.owner_dept ?? "IT");
  const [aud, setAud] = useState<string[]>(x.audience?.departments ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(action: "apply" | "reject" | "revert") {
    setBusy(true);
    setError(null);
    const edits = editing ? { sensitivity: sens, owner_dept: owner, audience: { departments: sens === "restricted" ? aud : [], sites: [] } } : null;
    const res = await fetch(`/api/policy/proposals/${p.id}/${action}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ edits }),
    }).catch(() => null);
    setBusy(false);
    if (!res) return setError("連不上伺服器");
    if (!res.ok) return setError(((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "操作失敗");
    router.refresh();
  }

  return (
    <article className="rounded-md border border-rule bg-tag p-4">
      <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
        <span className={p.status === "applied" ? "text-keep" : p.status === "invalid" ? "text-revoke" : "text-brass"}>{STATUS[p.status]}</span>
        <span className="min-w-0 break-words">{p.source === "classifier" ? `群組標註：${p.target}` : `「${p.prompt}」`}</span>
        {p.model && <span className="num ml-auto">{p.model}・{(p.elapsed_ms / 1000).toFixed(1)} 秒</span>}
      </div>
      <p className="mt-2 font-medium break-words">{describe(p)}</p>
      {p.rationale && <p className="mt-1 text-sm break-words text-muted">{p.rationale}</p>}
      {p.evidence.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {p.evidence.map((e, i) => <li key={i} className="rounded-sm bg-board px-1.5 py-0.5 text-xs break-all">「{e}」</li>)}
        </ul>
      )}
      {p.errors.length > 0 && (
        <ul className="mt-2 grid gap-0.5 text-xs text-revoke">{p.errors.map((e, i) => <li key={i} className="break-words">✗ {e}</li>)}</ul>
      )}
      {p.impact && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer">
            套用後：多出 <span className="num text-revoke">{p.impact.added}</span> 筆發現、消失 <span className="num text-keep">{p.impact.removed}</span> 筆
          </summary>
          <ul className="mt-2 grid max-h-48 gap-0.5 overflow-y-auto text-xs">
            {[...p.impact.added_rows.map((r) => ({ ...r, sign: "+" })), ...p.impact.removed_rows.map((r) => ({ ...r, sign: "−" }))].map((r, i) => (
              <li key={i} className="num flex min-w-0 gap-2">
                <span className={r.sign === "+" ? "text-revoke" : "text-keep"}>{r.sign}</span>
                <span className="truncate">{r.name ?? account(r.account)}{r.object && ` · ${r.object}`}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {editing && (
        <div className="mt-3 grid gap-2 border-t border-dashed border-rule pt-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <select value={sens} onChange={(e) => setSens(e.target.value)} aria-label="敏感度" className="rounded-sm border border-rule bg-white px-2 py-1">
              {Object.entries(SENSITIVITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="擁有部門" className="rounded-sm border border-rule bg-white px-2 py-1">
              {DEPTS.map((d) => <option key={d} value={d}>擁有：{dept(d)}</option>)}
            </select>
          </div>
          {sens === "restricted" && (
            <fieldset className="flex flex-wrap gap-1.5">
              <legend className="mb-1 text-xs text-muted">可以存取的部門</legend>
              {DEPTS.map((d) => (
                <button key={d} type="button" aria-pressed={aud.includes(d)} onClick={() => setAud(aud.includes(d) ? aud.filter((a) => a !== d) : [...aud, d])}
                  className={`rounded-sm border px-2 py-0.5 text-xs ${aud.includes(d) ? "border-brass bg-brass-wash" : "border-rule bg-white"}`}>{dept(d)}</button>
              ))}
            </fieldset>
          )}
        </div>
      )}
      {error && <p role="alert" className="mt-2 text-sm break-words text-revoke">{error}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {(p.status === "proposed" || (p.status === "invalid" && editing)) && (
          <button disabled={busy} onClick={() => act("apply")} className="rounded-sm bg-cabinet px-3 py-1 text-sm text-white hover:bg-ink disabled:opacity-50">
            {editing ? "修改後套用" : "套用"}
          </button>
        )}
        {editable && !editing && <button onClick={() => setEditing(true)} className="rounded-sm border border-rule bg-white px-3 py-1 text-sm hover:border-brass">修改</button>}
        {(p.status === "proposed" || p.status === "invalid" || p.status === "clarify") && (
          <button disabled={busy} onClick={() => act("reject")} className="rounded-sm border border-rule bg-white px-3 py-1 text-sm hover:border-brass disabled:opacity-50">捨棄</button>
        )}
        {p.status === "applied" && (
          <button disabled={busy} onClick={() => act("revert")} className="rounded-sm border border-rule bg-white px-3 py-1 text-sm hover:border-revoke disabled:opacity-50">撤回這條規則</button>
        )}
      </div>
    </article>
  );
}
