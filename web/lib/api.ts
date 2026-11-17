import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

const BACKEND = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8390";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const cookie = (await cookies()).toString();
  const res = await fetch(`${BACKEND}${path}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 401) redirect("/login");
  // 一般員工手動輸入 IT 專用頁面的網址：導回自己的覆核頁，不顯示錯誤頁
  if (res.status === 403) redirect("/reviews");
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(res.status, body.detail ?? "讀取資料失敗");
  }
  return (await res.json()) as T;
}
