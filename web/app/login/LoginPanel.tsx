"use client";

import { useState } from "react";
import { site } from "@/lib/format";
import type { DemoAccount } from "@/lib/types";

export function LoginPanel({ accounts }: { accounts: DemoAccount[] | null }) {
  const [id, setId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/auth/demo-login", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ employee_id: id.trim() }),
    }).catch(() => null);
    setBusy(false);
    if (!res) return setError("連不上伺服器，請確認 API 已啟動");
    if (!res.ok) return setError(((await res.json().catch(() => ({}))) as { detail?: string }).detail ?? "登入失敗");
    const me = (await res.json()) as { is_admin: boolean };
    // next 只接受站內路徑，避免登入頁被當成導去外部網站的跳板（//evil、/\evil 都會被瀏覽器當成外部網址）
    const next = new URLSearchParams(window.location.search).get("next");
    const safe = next && /^\/(?![/\\])/.test(next) ? next : null;
    window.location.replace(safe ?? (me.is_admin ? "/campaigns" : "/reviews"));
  }

  return (
    <div className="grid gap-10 md:grid-cols-[1fr_22rem]">
      <section className="min-w-0">
        <p className="font-tag text-5xl font-semibold tracking-[0.25em]">KEYWARD</p>
        <h1 className="mt-4 text-2xl break-words">誰還拿著不該有的鑰匙</h1>
        <p className="mt-3 max-w-lg text-muted break-words">
          每季一次，把 Entra ID、GitHub、ERP 上的帳號和權限對回 HR 名冊。規則找出問題，主管決定保留或撤銷，
          撤銷之後重新讀取，確認真的收回了。
        </p>
        {accounts && (
          <div className="mt-8">
            <p className="mb-2 text-sm text-muted">示範身分（點一下帶入）</p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {accounts.map((a) => (
                <li key={a.employee_id} className="min-w-0">
                  <button type="button" onClick={() => setId(a.employee_id)}
                    className={`w-full rounded-md border px-3 py-2 text-left hover:border-brass ${id === a.employee_id ? "border-brass bg-brass-wash" : "border-rule bg-tag"}`}>
                    <span className="block truncate font-medium">{a.name}<span className="num ml-2 text-xs text-muted">{a.employee_id}</span></span>
                    <span className="block truncate text-xs text-muted">{a.role}・{site(a.site)} {a.title}</span>
                    <span className="mt-1 block text-xs break-words">
                      {a.pending ? `${a.pending} 項待決定：${a.rules.join("、")}` : "目前沒有待辦"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {accounts.length <= 2 && (
              <p className="mt-2 text-xs break-words text-muted">先用資安負責人登入、建立一次覆核活動，主管的身分才會出現在這裡。</p>
            )}
          </div>
        )}
      </section>
      <form onSubmit={submit} className="self-center rounded-md border border-rule bg-tag p-6">
        <h2 className="text-xl font-medium">登入</h2>
        <label className="mt-4 block text-sm text-muted" htmlFor="emp">員工編號</label>
        <input id="emp" value={id} onChange={(e) => setId(e.target.value)} required maxLength={20} autoComplete="username"
          className="num mt-1 w-full rounded-sm border border-rule bg-white px-3 py-2 focus:border-brass focus:outline-none" />
        <p className="mt-1.5 text-xs break-words text-muted">
          {accounts ? "示範模式：輸入 HR 名冊上任一位在職員工的編號即可。正式環境改用 Entra ID 登入。" : "這個環境沒有開放示範登入。"}
        </p>
        {error && <p role="alert" className="mt-3 text-sm text-revoke">{error}</p>}
        <button disabled={busy || !accounts} className="mt-6 w-full rounded-sm bg-cabinet py-2.5 text-white hover:bg-ink disabled:opacity-50">
          {busy ? "登入中…" : "登入"}
        </button>
      </form>
    </div>
  );
}
