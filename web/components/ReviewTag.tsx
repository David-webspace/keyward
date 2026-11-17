"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { DECISION_LABEL, account, day } from "@/lib/format";
import type { ReviewItem } from "@/lib/types";

const NEEDS_DATE = new Set(["guest_access", "guest_github"]);

export function ReviewTag({ item, canDecide }: { item: ReviewItem; canDecide: boolean }) {
  const router = useRouter();
  const [choice, setChoice] = useState<"keep" | "revoke" | null>(null);
  const [groups, setGroups] = useState<Record<string, "keep" | "revoke">>(
    Object.fromEntries((item.groups ?? []).map((g) => [g, "revoke"])),
  );
  const [reason, setReason] = useState("");
  const [until, setUntil] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const perGroup = item.groups !== null;
  const keeping = perGroup ? Object.values(groups).includes("keep") : choice === "keep";
  const ready = perGroup || choice !== null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = perGroup ? { groups, reason } : { decision: choice, reason, keep_until: until || null };
    const res = await fetch(`/api/reviews/${item.id}/decision`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    }).catch(() => null);
    setBusy(false);
    if (!res) return setError("連不上伺服器，請稍後再試");
    if (!res.ok) return setError(((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "送出失敗");
    router.refresh();
  }

  const decided = item.decision;
  return (
    <article className="tag" data-decision={decided ?? undefined}>
      <div className="tag-stub" aria-hidden>
        <span className="tag-hole" />
        <span className="tag-no">NO. {String(item.id).padStart(4, "0")}</span>
      </div>
      <div className="min-w-0 p-4 pr-5">
        {decided && (
          <span className={`stamp ${decided === "keep" ? "text-keep" : "text-revoke"}`}>{DECISION_LABEL[decided]}</span>
        )}
        <p className={`text-xs tracking-wide text-brass ${decided ? "pr-28" : ""}`}>{item.label}</p>
        <h3 className={`mt-1 font-medium break-words ${decided ? "pr-28" : ""}`}>
          {item.subject_name ?? account(item.account)}
        </h3>
        {(item.subject_name || item.object) && (
          <p className="num mt-0.5 text-xs break-all text-muted">{item.subject_name && account(item.account)}{item.subject_name && item.object && " · "}{item.object}</p>
        )}
        <p className="mt-3 text-sm leading-relaxed break-words">{item.explanation}</p>
        <p className="mt-3 text-xs text-muted">
          期限 <span className="num">{day(item.due_at)}</span>
          {item.level > 0 && <span className="ml-2 text-revoke">已逾期升級 {item.level} 次</span>}
          {item.status === "overdue" && <span className="ml-2 text-revoke">逾期，等待資安處理</span>}
        </p>
        {decided && item.decision_detail.groups && (
          <ul className="mt-2 grid gap-0.5 text-xs">
            {Object.entries(item.decision_detail.groups).map(([g, d]) => (
              <li key={g} className="num flex min-w-0 gap-2">
                <span className={`shrink-0 ${d === "keep" ? "text-keep" : "text-revoke"}`}>{DECISION_LABEL[d]}</span>
                <span className="truncate">{g}</span>
              </li>
            ))}
          </ul>
        )}
        {decided && item.reason && <p className="mt-2 text-xs break-words text-muted">理由：{item.reason}</p>}
        {!decided && canDecide && (
          <form onSubmit={submit} className="mt-4 border-t border-dashed border-rule pt-4">
            {perGroup ? (
              <fieldset className="grid gap-1.5">
                <legend className="mb-1 text-sm text-muted">每個群組各自決定</legend>
                {item.groups!.map((g) => (
                  <div key={g} className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="num min-w-0 flex-1 truncate text-sm">{g}</span>
                    {(["keep", "revoke"] as const).map((d) => (
                      <button key={d} type="button" aria-pressed={groups[g] === d} onClick={() => setGroups({ ...groups, [g]: d })}
                        className={`rounded-sm border px-2.5 py-0.5 text-xs ${groups[g] === d ? (d === "keep" ? "border-keep bg-keep-wash text-keep" : "border-revoke bg-revoke-wash text-revoke") : "border-rule"}`}>
                        {DECISION_LABEL[d]}
                      </button>
                    ))}
                  </div>
                ))}
              </fieldset>
            ) : (
              <div className="flex gap-2">
                {(["revoke", "keep"] as const).map((d) => (
                  <button key={d} type="button" aria-pressed={choice === d} onClick={() => setChoice(d)}
                    className={`rounded-sm border px-4 py-1.5 text-sm ${choice === d ? (d === "keep" ? "border-keep bg-keep-wash text-keep" : "border-revoke bg-revoke-wash text-revoke") : "border-rule bg-white"}`}>
                    {DECISION_LABEL[d]}
                  </button>
                ))}
              </div>
            )}
            {keeping && (
              <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_11rem]">
                <label className="min-w-0 text-xs text-muted">
                  保留的理由（稽核會看到）
                  <textarea value={reason} onChange={(e) => setReason(e.target.value)} required minLength={5} maxLength={2000} rows={2}
                    className="mt-1 w-full rounded-sm border border-rule bg-white px-2 py-1.5 text-sm text-ink focus:border-brass focus:outline-none" />
                </label>
                {!perGroup && (
                  <label className="text-xs text-muted">
                    {NEEDS_DATE.has(item.rule) ? "新的到期日（必填）" : "下次檢查（預設 180 天）"}
                    <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} required={NEEDS_DATE.has(item.rule)}
                      className="num mt-1 w-full rounded-sm border border-rule bg-white px-2 py-1.5 text-sm text-ink" />
                  </label>
                )}
              </div>
            )}
            {error && <p role="alert" className="mt-2 text-sm break-words text-revoke">{error}</p>}
            {ready && (
              <button disabled={busy} className="mt-3 rounded-sm bg-cabinet px-4 py-1.5 text-sm text-white hover:bg-ink disabled:opacity-50">
                {busy ? "送出中…" : "確認決定"}
              </button>
            )}
          </form>
        )}
      </div>
    </article>
  );
}
