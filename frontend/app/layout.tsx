import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DRL vs LLM/Agentic Trading — VN30",
  description: "Comparison dashboard for 8 trading agents on Vietnamese VN30 (PKG-13).",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="bg-gray-50 text-gray-900 min-h-full flex flex-col">
        {children}
      </body>
    </html>
  );
}
