import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "DRL vs LLM/Agentic Trading — VN30",
  description: "Comparison dashboard for 8 trading agents on Vietnamese VN30 (PKG-13+).",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="bg-gray-50 text-gray-900 min-h-full flex flex-col">
        {/* PKG-15: cross-page nav. Single source for site navigation. */}
        <nav className="border-b border-gray-200 bg-white">
          <div className="container mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 text-sm">
            <Link href="/" className="font-semibold hover:underline">
              Dashboard
            </Link>
            <Link href="/debate" className="hover:underline">
              Debate
            </Link>
            <Link href="/live" className="hover:underline">
              Live
            </Link>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
