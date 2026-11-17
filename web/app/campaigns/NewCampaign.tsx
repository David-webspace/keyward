"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function NewCampaign() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [asOf, setAsOf] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/campaigns", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name, as_of: asOf || null }),
    }).catch(() => null);
    setBusy(false);
    if (!res) return setError("連不上伺服器");
    const data = (await res.json().catch(() => ({}))) as { id?: number; detail?: string };
    if (!res.ok || !data.id) return setError(data.detail ?? "建立失敗");
    router.push(`/campaigns/${data.id}`);
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-md border border-rule bg-tag p-4 sm:grid-cols-[1fr_11rem_auto] sm:items-end">
      <label className="min-w-0 text-xs text-muted">
        活動名稱
        <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={200} placeholder="例如：2026 第四季權限覆核"
          className="mt-1 w-full rounded-sm border border-rule bg-white px-2 py-1.5 text-sm text-ink focus:border-brass focus:outline-none" />
      </label>
      <label className="text-xs text-muted">
        資料基準日（預設今天）
        <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
          className="num mt-1 w-full rounded-sm border border-rule bg-white px-2 py-1.5 text-sm text-ink" />
      </label>
      <button disabled={busy} className="rounded-sm bg-cabinet px-4 py-2 text-sm text-white hover:bg-ink disabled:opacity-50">
        {busy ? "分派中…" : "用最新同步建立並分派"}
      </button>
      {error && <p role="alert" className="text-sm text-revoke sm:col-span-3">{error}</p>}
    </form>
  );
}
