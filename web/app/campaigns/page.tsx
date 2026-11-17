import Link from "next/link";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import { day } from "@/lib/format";
import type { CampaignSummary } from "@/lib/types";
import { NewCampaign } from "./NewCampaign";

export default async function CampaignsPage() {
  const list = await apiGet<CampaignSummary[]>("/campaigns");
  return (
    <Shell title="覆核活動" lead="從最新一次同步的發現建立活動，系統依 HR 主管關係分派，每位覆核者收到一封彙整信。">
      <NewCampaign />
      <ul className="mt-6 grid gap-3">
        {list.map((c) => {
          const done = c.by_status.decided ?? 0;
          return (
            <li key={c.id} className="min-w-0">
              <Link href={`/campaigns/${c.id}`} className="block rounded-md border border-rule bg-tag p-4 hover:border-brass">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="font-medium break-words">{c.name}</span>
                  <span className="num text-xs text-muted">基準日 {day(c.as_of)}</span>
                  <span className="ml-auto text-xs text-muted">{c.status === "handed_off" ? "已交付執行" : "進行中"}</span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-board" aria-hidden>
                  <div className="h-full bg-brass" style={{ width: `${c.total ? (done / c.total) * 100 : 0}%` }} />
                </div>
                <p className="num mt-1.5 text-xs text-muted">{done} / {c.total} 已決定・升級 {c.escalated}・逾期 {c.by_status.overdue ?? 0}</p>
              </Link>
            </li>
          );
        })}
        {list.length === 0 && <li className="rounded-md border border-dashed border-rule p-8 text-center text-muted">還沒有覆核活動。先執行一次同步，再用上面的表單建立。</li>}
      </ul>
    </Shell>
  );
}
