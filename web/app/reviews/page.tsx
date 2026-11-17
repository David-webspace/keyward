import Link from "next/link";
import { ReviewTag } from "@/components/ReviewTag";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { ReviewItem } from "@/lib/types";

const TABS = [
  { status: "pending", label: "待決定" },
  { status: "decided", label: "已決定" },
  { status: "overdue", label: "已逾期" },
];

export default async function ReviewsPage({ searchParams }: PageProps<"/reviews">) {
  const raw = (await searchParams).status;
  const status = TABS.some((t) => t.status === raw) ? (raw as string) : "pending";
  const items = await apiGet<ReviewItem[]>(`/reviews?status=${status}`);
  return (
    <Shell title="我的覆核" lead="這些人或帳號的存取權需要您決定。撤銷會交給 IT 執行並重新確認；保留需要寫下理由，到期後會再請您確認一次。">
      <nav className="mb-5 flex gap-1 border-b border-rule">
        {TABS.map((t) => (
          <Link key={t.status} href={`/reviews?status=${t.status}`} aria-current={t.status === status ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${t.status === status ? "border-brass font-medium" : "border-transparent text-muted hover:text-ink"}`}>
            {t.label}
          </Link>
        ))}
      </nav>
      {items.length === 0 ? (
        <p className="rounded-md border border-dashed border-rule p-8 text-center text-muted">
          {status === "pending" ? "沒有需要您決定的項目。" : "這裡目前是空的。"}
        </p>
      ) : (
        <ul className="grid gap-4 lg:grid-cols-2">
          {items.map((i) => (
            <li key={i.id} className="min-w-0"><ReviewTag item={i} canDecide={status === "pending"} /></li>
          ))}
        </ul>
      )}
    </Shell>
  );
}
