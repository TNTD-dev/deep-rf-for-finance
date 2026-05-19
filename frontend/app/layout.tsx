import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { SiteNav } from "@/components/SiteNav";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jbm = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jbm",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Intelligence Core — DRL vs LLM Agentic Trading on VN30",
  description:
    "8 trading agents benchmarked on Vietnam's VN30 market: classical baselines, DDPG/PPO reinforcement learning, and zero-shot / single-agentic / multi-agent LLM systems. Replay debates, run live, compare full-period results.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className={`dark ${inter.variable} ${jbm.variable}`}>
      <body className="min-h-screen flex flex-col relative">
        <SiteNav />
        <div className="relative z-10 flex-1">{children}</div>
      </body>
    </html>
  );
}
