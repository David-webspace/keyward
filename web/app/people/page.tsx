import Link from "next/link";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import { site } from "@/lib/format";
import type { PersonHit } from "@/lib/types";

export default async function PeoplePage({ searchParams }: PageProps<"/people">) {
  const raw = (await searchParams).q;
  const q = typeof raw === "string" ? raw.slice(0, 50) : "";
  const hits = q ? await apiGet<PersonHit[]>(`/people?q=${encodeURIComponent(q)}`) : [];
  return (
    <Shell title="查人" lead="輸入姓名、英文名、Email 或員工編號，看一個人在 Entra ID、GitHub、ERP 上的所有權限。">
      <form className="flex max-w-lg gap-2">
        <input name="q" defaultValue={q} maxLength={50} placeholder="例如：Chen、E14017" aria-label="搜尋員工"
          className="min-w-0 flex-1 rounded-sm border border-rule bg-white px-3 py-2 focus:border-brass focus:outline-none" />
        <button className="rounded-sm bg-cabinet px-4 text-sm text-white hover:bg-ink">搜尋</button>
      </form>
      {q && (
        <ul className="mt-5 grid gap-2 sm:grid-cols-2">
          {hits.map((p) => (
            <li key={p.employee_id} className="min-w-0">
              <Link href={`/people/${p.employee_id}`} className="block rounded-md border border-rule bg-tag px-3 py-2 hover:border-brass">
                <span className="block truncate font-medium">{p.name}<span className="num ml-2 text-xs text-muted">{p.employee_id}</span></span>
                <span className="block truncate text-xs text-muted">{site(p.site)} {p.title}{p.status !== "active" && `・${p.status === "leave" ? "留職停薪" : "已離職"}`}</span>
              </Link>
            </li>
          ))}
          {hits.length === 0 && <li className="text-muted">找不到符合「{q}」的人。</li>}
        </ul>
      )}
    </Shell>
  );
}
