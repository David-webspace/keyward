"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

// 呼叫一個 POST API，成功後重新整理頁面資料。done 是結果訊息樣板，{欄位} 會換成回應裡的值
// （伺服器元件不能把函式傳給 client 元件，所以用樣板）
export function PostButton({ url, body, label, busyLabel, done, confirm, primary }: {
  url: string;
  body?: object;
  label: string;
  busyLabel: string;
  done: string;
  confirm?: string;
  primary?: boolean;
}) {
  const router = useRouter();
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    if (confirm && !window.confirm(confirm)) return;
    setBusy(true);
    const res = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body ?? {}) })
      .catch(() => null);
    setBusy(false);
    if (!res) return setMsg({ ok: false, text: "連不上伺服器" });
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) return setMsg({ ok: false, text: (data.detail as string) ?? "操作失敗" });
    setMsg({ ok: true, text: done.replace(/\{(\w+)\}/g, (_, k: string) => String(data[k] ?? "")) });
    router.refresh();
  }

  return (
    <div className="min-w-0">
      <button onClick={run} disabled={busy}
        className={`rounded-sm px-4 py-1.5 text-sm disabled:opacity-50 ${primary ? "bg-cabinet text-white hover:bg-ink" : "border border-rule bg-white hover:border-brass"}`}>
        {busy ? busyLabel : label}
      </button>
      {msg && <p role="status" className={`mt-1.5 text-xs break-words ${msg.ok ? "text-keep" : "text-revoke"}`}>{msg.text}</p>}
    </div>
  );
}
