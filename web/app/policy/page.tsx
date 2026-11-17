import { PostButton } from "@/components/PostButton";
import { ProposalCard } from "@/components/ProposalCard";
import { Shell } from "@/components/Shell";
import { apiGet } from "@/lib/api";
import type { PolicyState } from "@/lib/types";
import { RuleDraft } from "./RuleDraft";

const OPEN = new Set(["proposed", "invalid", "clarify"]);

export default async function PolicyPage() {
  const s = await apiGet<PolicyState>("/policy");
  const sentences = s.proposals.filter((p) => p.source === "sentence" && OPEN.has(p.status));
  const labels = s.proposals.filter((p) => p.source === "classifier" && OPEN.has(p.status))
    .sort((a, b) => Number(b.proposal.sensitivity === "restricted") - Number(a.proposal.sensitivity === "restricted"));
  const applied = s.proposals.filter((p) => p.status === "applied");
  return (
    <Shell title="規則" lead={<>基礎規則在 policy.yaml。這裡的提案由 AI 產生，經程式驗證與影響預覽，<b className="font-medium text-ink">IT 按下套用才會生效</b>，隨時可以撤回。模型不參與任何「誰該撤權」的判斷。</>}>
      {s.ai_message && <p role="status" className="mb-5 rounded-md border border-brass bg-brass-wash px-4 py-2 text-sm break-words">{s.ai_message}</p>}
      <div className="grid gap-8 lg:grid-cols-2">
        <section className="min-w-0">
          <RuleDraft disabled={!!s.ai_message} />
          <ul className="mt-4 grid gap-3">
            {sentences.map((p) => <li key={p.id} className="min-w-0"><ProposalCard p={p} /></li>)}
          </ul>
        </section>
        <section className="min-w-0">
          <div className="rounded-md border border-rule bg-tag p-4">
            <h2 className="font-medium">群組標註</h2>
            <p className="mt-1 text-sm break-words text-muted">
              還有 <span className="num">{s.unlabeled}</span> 個群組不在任何規則裡，系統看不出它們是否敏感。請 AI 依名稱、說明與成員的部門分布提出建議；標成限制級並套用後，不該有存取權的人就會出現在發現裡。
            </p>
            <div className="mt-3">
              <PostButton url="/api/policy/groups/suggest" body={{ limit: 5 }} label="請 AI 標註 5 個群組" busyLabel="標註中（每個約 10 秒）…"
                done="完成，還有 {remaining} 個群組沒有標註" primary />
            </div>
          </div>
          <ul className="mt-4 grid gap-3">
            {labels.map((p) => <li key={p.id} className="min-w-0"><ProposalCard p={p} /></li>)}
          </ul>
        </section>
      </div>
      <section className="mt-10 border-t border-rule pt-6">
        <h2 className="font-medium">已生效的規則（疊加在 policy.yaml 上）</h2>
        {applied.length === 0 ? <p className="mt-2 text-sm text-muted">還沒有套用任何提案。</p> : (
          <ul className="mt-3 grid gap-3 lg:grid-cols-2">
            {applied.map((p) => <li key={p.id} className="min-w-0"><ProposalCard p={p} /></li>)}
          </ul>
        )}
      </section>
    </Shell>
  );
}
