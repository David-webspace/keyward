import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "keyward",
  description: "跨平台帳號權限盤點：找出不該有的存取權，交給主管決定，安全地收回",
};

export const viewport: Viewport = { themeColor: "#1e2b2a" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-Hant-TW" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
