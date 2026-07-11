import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Ashr Release Console",
  description: "A3 product console for agent evaluation, review, reports, and release governance."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
