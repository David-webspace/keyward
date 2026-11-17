import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// 只做「有沒有 cookie」的樂觀檢查；真正的身分與權限驗證在後端每個 API
export function proxy(request: NextRequest) {
  if (!request.cookies.has("keyward_session")) {
    const login = new URL("/login", request.url);
    if (request.nextUrl.pathname !== "/") login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|api|_next|favicon.ico).*)"],
};
