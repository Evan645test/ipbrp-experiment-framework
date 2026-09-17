import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "頁間 · 論文導讀與逐段精讀",
  description: "集中開啟八篇互動論文導讀，切換逐段精讀並對照原始 PDF、中文翻譯與圖表。",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant">
      <body className="antialiased">{children}</body>
    </html>
  );
}
