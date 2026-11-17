import { notFound } from "next/navigation";
import { Shell } from "@/components/Shell";
import { ApiError, apiGet } from "@/lib/api";
import { day, dept, site } from "@/lib/format";
import type { Profile } from "@/lib/types";

const STATUS = { active: "在職", leave: "留職停薪", terminated: "已離職" } as Record<string, string>;
const RULE = {
  transfer_residual: "轉調未收回", resource_access: "不符資格的資源", inactive_account: "長期未登入", peer_outlier: "同儕離群",
  sod_conflict: "職責分離衝突", excess_admin: "管理員角色不符資格", terminated_enabled: "已離職仍啟用", terminated_github: "已離職仍在 GitHub",
  github_no_2fa: "未開 2FA", unlinked_github: "身分未確認",
} as Record<string, string>;

function Ring({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0 rounded-md border border-rule bg-tag p-4">
      <h2 className="mb-3 flex items-center gap-2 font-medium"><span className="tag-hole scale-75" aria-hidden />{title}</h2>
      {children}
    </section>
  );
}

export default async function PersonPage({ params }: PageProps<"/people/[id]">) {
  const { id } = await params;
  const p = await apiGet<Profile>(`/people/${encodeURIComponent(id)}`).catch((e: unknown) => {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  });
  const flagged = new Set(p.findings.map((f) => f.object).filter(Boolean));
  return (
    <Shell title={p.name} lead={<>{p.en_name}・{site(p.site)} {dept(p.dept)} {p.title}・<span className="num">{p.employee_id}</span>・{STATUS[p.status] ?? p.status}{p.employment_type === "contract" && "・約聘"}</>}>
      {p.findings.length > 0 && (
        <ul className="mb-6 flex flex-wrap gap-2">
          {p.findings.map((f, i) => (
            <li key={i} className="rounded-full border border-revoke bg-revoke-wash px-3 py-1 text-xs text-revoke break-words">
              {RULE[f.rule] ?? f.rule}{f.object && `：${f.object}`}
            </li>
          ))}
        </ul>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Ring title="HR 名冊">
          <dl className="grid grid-cols-[6rem_1fr] gap-y-1.5 text-sm">
            <dt className="text-muted">主管</dt><dd className="min-w-0 break-words">{p.manager?.name ?? "—"}</dd>
            <dt className="text-muted">到職</dt><dd className="num">{day(p.hire_date)}</dd>
            <dt className="text-muted">離職</dt><dd className="num">{day(p.termination_date)}</dd>
            <dt className="text-muted">Email</dt><dd className="num min-w-0 break-all text-xs">{p.email}</dd>
          </dl>
          {p.transfers.length > 0 && (
            <ul className="mt-3 grid gap-1 border-t border-dashed border-rule pt-3 text-xs">
              {p.transfers.map((t, i) => (
                <li key={i} className="num break-words">
                  {t.effective_date} {t.from_site}-{t.from_dept} → {t.to_site}-{t.to_dept}{t.kind === "temporary" && `（支援至 ${t.end_date}）`}
                </li>
              ))}
            </ul>
          )}
        </Ring>
        {p.entra.map((a) => (
          <Ring key={a.upn} title="Entra ID">
            <p className="num text-xs break-all">{a.upn}</p>
            <p className="mt-1 text-sm">{a.enabled ? "啟用中" : "已停用"}・最後登入 <span className="num">{day(a.last_sign_in)}</span></p>
            {a.roles.length > 0 && <p className="mt-2 text-sm text-revoke break-words">目錄角色：{a.roles.join("、")}</p>}
            <h3 className="mt-3 text-xs text-muted">直接加入的群組</h3>
            <ul className="mt-1 grid gap-1 text-sm">
              {a.direct_groups.map((g) => (
                <li key={g.name} className={`min-w-0 break-words ${flagged.has(g.name) ? "text-revoke" : ""}`}>
                  <span className="num text-xs">{g.name}</span>{g.description && <span className="ml-2 text-xs text-muted">{g.description}</span>}
                </li>
              ))}
            </ul>
            <h3 className="mt-3 text-xs text-muted">因此間接取得</h3>
            <ul className="mt-1 grid gap-1 text-xs">
              {a.inherited_groups.map((g) => (
                <li key={g.name} className="num min-w-0 break-words">{g.name}<span className="ml-2 text-muted">經由 {g.via.join("、")}</span></li>
              ))}
            </ul>
          </Ring>
        ))}
        <Ring title="GitHub">
          {p.github.length === 0 ? <p className="text-sm text-muted">沒有對應的 GitHub 帳號。</p> : (
            <ul className="grid gap-1 text-sm">
              {p.github.map((g) => (
                <li key={g.login} className="break-words">
                  <span className="num">{g.login}</span>
                  <span className="ml-2 text-xs text-muted">{g.kind === "outside" ? "外部協作者" : g.role === "admin" ? "管理員" : "成員"}・{g.two_factor === false ? "未開 2FA" : "已開 2FA"}・{g.confirmed ? `對應方式 ${g.matched_by}` : "身分未確認"}</span>
                </li>
              ))}
            </ul>
          )}
        </Ring>
        <Ring title="ERP">
          {p.erp.length === 0 ? <p className="text-sm text-muted">沒有 ERP 角色。</p> : (
            <ul className="grid gap-1 text-sm">
              {p.erp.map((r) => <li key={r.role} className="break-words"><span className="num">{r.role}</span><span className="num ml-2 text-xs text-muted">{r.transactions.join(" · ")}</span></li>)}
            </ul>
          )}
        </Ring>
      </div>
    </Shell>
  );
}
