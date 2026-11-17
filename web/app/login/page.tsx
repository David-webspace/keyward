import type { DemoAccount } from "@/lib/types";
import { LoginPanel } from "./LoginPanel";

const BACKEND = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8390";

async function demoAccounts(): Promise<DemoAccount[] | null> {
  const res = await fetch(`${BACKEND}/demo/accounts`, { cache: "no-store" }).catch(() => null);
  return res?.ok ? ((await res.json()) as DemoAccount[]) : null;
}

export default async function LoginPage() {
  return (
    <main className="mx-auto grid min-h-dvh max-w-5xl items-center px-4 py-10">
      <LoginPanel accounts={await demoAccounts()} />
    </main>
  );
}
