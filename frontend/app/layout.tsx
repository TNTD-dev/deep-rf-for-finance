import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Space_Grotesk } from "next/font/google";

import { SiteNav } from "@/components/SiteNav";

import "./globals.css";

// Trading-platform typography:
//   Inter        → body, paragraphs (legible at small sizes)
//   Space Grotesk → display + headlines (engineered, technical feel)
//   JetBrains Mono → numbers, tickers, labels (tabular data)
// All loaded via next/font/google so CLS is zero and they ship self-hosted.

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const grotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-grotesk",
  display: "swap",
});

const jbm = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jbm",
  display: "swap",
});

export const metadata: Metadata = {
  title: "QuantArena — 8 Agents, 1 Benchmark · VN30",
  description:
    "Battle of the trading minds on Vietnam's VN30 market. Three classical baselines, DDPG & PPO reinforcement learning, and three LLM systems — zero-shot, single-agentic, and an 8-role multi-agent debate — benchmarked across a full 12-month out-of-sample window.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className={`dark ${inter.variable} ${grotesk.variable} ${jbm.variable}`} suppressHydrationWarning>
      <body className="min-h-screen flex flex-col relative">
        <SiteNav />
        <div className="relative z-10 flex-1">{children}</div>
      </body>
    </html>
  );
}
