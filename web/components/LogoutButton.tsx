"use client";

export function LogoutButton() {
  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => null);
    window.location.replace("/login");
  }
  return (
    <button onClick={logout} className="rounded-sm border border-white/30 px-2 py-0.5 text-xs hover:bg-white/10">登出</button>
  );
}
