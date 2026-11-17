import Link from "next/link";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import { account, dateTime, day } from "@/lib/format";
import type { Findings } from "@/lib/types";

export default async function FindingsPage({ searchParams }: PageProps<"/findings">) {
  const sp = await searchParams;
  const rule = typeof sp.rule === "string" ? sp.rule : null;
  const asOf = typeof sp.as_of === "string" && /^\d{4}-\d{2}-\d{2}$/.test(sp.as_of) ? sp.as_of : null;
  const data = await apiGet<Findings>(`/findings${asOf ? `?as_of=${asOf}` : ""}`);
  const counts = new Map<string, { label: string; n: number }>();
  for (const f of data.items) counts.set(f.rule, { label: f.label, n: (counts.get(f.rule)?.n ?? 0) + 1 });
  const rows = rule ? data.items.filter((f) => f.rule === rule) : data.items;
  const q = (r: string | null) => `/findings?${new URLSearchParams({ ...(r ? { rule: r } : {}), ...(asOf ? { as_of: asOf } : {}) })}`;

  return (
    <Shell title="發現" lead={<>
      系統依目前的權限規則，找出不該存在的帳號與存取權。判斷完全由規則決定，不經過 AI。
      <span className="mt-1 block text-sm">
        資料更新於 <span className="num">{dateTime(data.taken_at)}</span>，以 <span className="num">{day(data.as_of)}</span> 為判斷日期
        {data.suppressed > 0 && <>；另有 {data.suppressed} 項主管已決定保留，到期前不列出</>}。
      </span>
    </>}>
      <nav className="flex flex-wrap gap-2">
        <Link href={q(null)} className={`rounded-full border px-3 py-1 text-xs ${!rule ? "border-brass bg-brass-wash" : "border-rule bg-tag"}`}>
          全部 <span className="num">{data.items.length}</span>
        </Link>
        {[...counts].map(([r, c]) => (
          <Link key={r} href={q(r)} className={`rounded-full border px-3 py-1 text-xs ${rule === r ? "border-brass bg-brass-wash" : "border-rule bg-tag"}`}>
            {c.label} <span className="num">{c.n}</span>
          </Link>
        ))}
      </nav>
      <div className="mt-5 overflow-x-auto rounded-md border border-rule bg-tag">
        <table className="w-full min-w-[40rem] text-sm">
          <thead className="text-left text-xs text-muted">
            <tr><th className="px-3 py-2 font-normal">類型</th><th className="px-3 py-2 font-normal">人</th><th className="px-3 py-2 font-normal">帳號／物件</th><th className="px-3 py-2 font-normal">系統</th></tr>
          </thead>
          <tbody>
            {rows.map((f, i) => (
              <tr key={`${f.rule}-${f.account}-${f.object}-${i}`} className="border-t border-rule align-top">
                <td className="px-3 py-2 break-words">{f.label}{!f.confirmed && <span className="ml-1.5 text-xs text-brass">需確認身分</span>}</td>
                <td className="px-3 py-2">
                  {f.employee_id ? <Link href={`/people/${f.employee_id}`} className="underline decoration-rule underline-offset-4 hover:decoration-brass">{f.name}</Link> : <span className="text-muted">—</span>}
                </td>
                <td className="num px-3 py-2 text-xs break-all">{account(f.account)}{f.object && <span className="block text-muted">{f.object}</span>}</td>
                <td className="px-3 py-2 text-xs text-muted">{f.system}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
