import { notFound } from "next/navigation";
import { PostButton } from "@/components/PostButton";
import { Shell } from "@/components/Shell";
import { ApiError, apiGet } from "@/lib/api";
import { DECISION_LABEL, day } from "@/lib/format";
import type { CampaignDetail } from "@/lib/types";
import { TickForm } from "./TickForm";

const COLS = [
  { key: "pending", label: "待決定" },
  { key: "overdue", label: "逾期" },
  { key: "revoke", label: DECISION_LABEL.revoke },
  { key: "partial", label: DECISION_LABEL.partial },
  { key: "keep", label: DECISION_LABEL.keep },
];
const EXEC_LABEL: Record<string, string> = {
  planned: "等 IT 核准", approved: "已核准待執行", verified: "已執行並驗證", verify_failed: "驗證失敗", failed: "失敗", blocked: "被保護規則擋下",
};

export default async function CampaignPage({ params }: PageProps<"/campaigns/[id]">) {
  const { id } = await params;
  const c = await apiGet<CampaignDetail>(`/campaigns/${encodeURIComponent(id)}`).catch((e: unknown) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const decided = c.by_status.decided ?? 0;
  return (
    <Shell title={c.name} lead={<>資料基準日 <span className="num">{day(c.as_of)}</span>・{c.total} 項需要覆核，另有 {c.direct} 項已離職的帳號依 HR 名冊直接處理{c.suppressed > 0 && `，${c.suppressed} 項因既有的保留例外沒有列入`}。</>}>
      <section className="grid gap-4 md:grid-cols-3">
        {[
          { label: "已決定", value: `${decided} / ${c.total}` },
          { label: "曾經逾期升級", value: c.escalated },
          { label: "仍在等待", value: (c.by_status.pending ?? 0) + (c.by_status.overdue ?? 0) },
        ].map((s) => (
          <div key={s.label} className="rounded-md border border-rule bg-tag p-4">
            <p className="text-xs text-muted">{s.label}</p>
            <p className="num mt-1 text-2xl">{s.value}</p>
          </div>
        ))}
      </section>

      <section className="mt-8 grid gap-8 lg:grid-cols-[1fr_18rem]">
        <div className="min-w-0 overflow-x-auto">
          <h2 className="mb-2 font-medium">依發現類型</h2>
          <table className="w-full min-w-[32rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1.5 font-normal">類型</th>{COLS.map((k) => <th key={k.key} className="py-1.5 text-right font-normal">{k.label}</th>)}</tr>
            </thead>
            <tbody>
              {c.by_rule.map((r) => (
                <tr key={r.rule} className="border-t border-rule">
                  <td className="py-2 pr-2 break-words">{r.label}</td>
                  {COLS.map((k) => <td key={k.key} className="num py-2 text-right">{(r[k.key] as number) || "·"}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="min-w-0">
          <h2 className="mb-2 font-medium">還在等誰</h2>
          <ul className="grid gap-1.5 text-sm">
            {c.waiting_on.map((w) => (
              <li key={w.employee_id} className="flex min-w-0 justify-between gap-2">
                <span className="truncate">{w.name}</span><span className="num shrink-0 text-muted">{w.open}</span>
              </li>
            ))}
            {c.waiting_on.length === 0 && <li className="text-muted">全部都決定了。</li>}
          </ul>
        </div>
      </section>

      <section className="mt-10 grid gap-6 border-t border-rule pt-6 md:grid-cols-3">
        <div className="min-w-0">
          <h2 className="font-medium">提醒與升級</h2>
          <p className="mt-1 mb-3 text-xs break-words text-muted">到期前 2 天提醒；逾期升級給上一層主管。逾期不會自動撤銷。</p>
          <TickForm id={c.id} />
        </div>
        <div className="min-w-0">
          <h2 className="font-medium">交付執行</h2>
          <p className="mt-1 mb-3 text-xs break-words text-muted">主管撤銷的項目以主管為核准者交給執行引擎；已離職與無法還原的動作仍需 IT 核准。</p>
          {c.execution ? (
            <ul className="grid gap-1 text-sm">
              {Object.entries(c.execution).map(([k, v]) => (
                <li key={k} className="flex justify-between gap-2"><span>{EXEC_LABEL[k] ?? k}</span><span className="num">{v}</span></li>
              ))}
            </ul>
          ) : (
            <PostButton url={`/api/campaigns/${c.id}/hand-off`} label="交付執行" busyLabel="產生執行計畫…" primary
              confirm="交付後就不能再改這個活動的決定。確定交付？"
              done="{actions} 個動作：{approved} 個已由主管核准，{awaiting_it} 個等 IT 核准，{manual} 個轉人工" />
          )}
        </div>
        <div className="min-w-0">
          <h2 className="font-medium">稽核證據包</h2>
          <p className="mt-1 mb-3 text-xs break-words text-muted">每個項目的覆核者、決定、理由、升級紀錄、寄出的通知與執行結果，CSV 格式。</p>
          <a href={`/api/campaigns/${c.id}/evidence`} className="inline-block rounded-sm border border-rule bg-white px-4 py-1.5 text-sm hover:border-brass">下載 zip</a>
        </div>
      </section>
    </Shell>
  );
}
