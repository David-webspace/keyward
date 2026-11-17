"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const EXAMPLES = ["薪資資料只有台北的人資和財務能看", "開工單的人不能自己做生產報工", "超過 60 天沒登入就算殭屍帳號"];

export function RuleDraft({ disabled }: { disabled: boolean }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/policy/drafts", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text }),
    }).catch(() => null);
    setBusy(false);
    if (!res) return setError("連不上伺服器");
    if (!res.ok) return setError(((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "轉換失敗");
    setText("");
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="rounded-md border border-rule bg-tag p-4">
      <label htmlFor="rule" className="text-sm font-medium">用一句話描述規則</label>
      <textarea id="rule" value={text} onChange={(e) => setText(e.target.value)} required minLength={4} maxLength={300} rows={2} disabled={disabled}
        className="mt-2 w-full rounded-sm border border-rule bg-white px-3 py-2 focus:border-brass focus:outline-none disabled:opacity-50" />
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" onClick={() => setText(ex)} disabled={disabled}
            className="rounded-full border border-rule bg-white px-2.5 py-0.5 text-xs hover:border-brass disabled:opacity-50">{ex}</button>
        ))}
      </div>
      {error && <p role="alert" className="mt-2 text-sm break-words text-revoke">{error}</p>}
      <button disabled={busy || disabled} className="mt-3 rounded-sm bg-cabinet px-4 py-1.5 text-sm text-white hover:bg-ink disabled:opacity-50">
        {busy ? "轉換並預覽影響中…" : "轉成規則草稿"}
      </button>
      <p className="mt-2 text-xs break-words text-muted">草稿會先經程式驗證，並用最新同步預覽套用後會多出哪些發現；按「套用」才會生效。</p>
    </form>
  );
}
