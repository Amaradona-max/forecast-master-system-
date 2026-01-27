import "./globals.css"

import type { Metadata } from "next"

import { ThemeProvider } from "@/components/theme/ThemeProvider"

export const metadata: Metadata = {
  title: "Forecast Master System",
  description: "Previsioni probabilistiche multi-campionato"
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="it" suppressHydrationWarning>
      <body className="min-h-screen bg-gradient-to-br from-zinc-50 via-zinc-100 to-zinc-50 text-zinc-900 antialiased dark:from-zinc-950 dark:via-zinc-900 dark:to-zinc-950 dark:text-zinc-50">
        <ThemeProvider>
          <div className="relative min-h-screen">
            <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
              <div className="absolute -left-32 -top-40 h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.18),transparent_70%)] blur-3xl animate-pulse-glow dark:bg-[radial-gradient(circle_at_center,rgba(52,211,153,0.15),transparent_70%)]" />
              <div className="absolute -right-32 -top-32 h-[36rem] w-[36rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.15),transparent_70%)] blur-3xl animate-pulse-glow animation-delay-1000 dark:bg-[radial-gradient(circle_at_center,rgba(129,140,248,0.12),transparent_70%)]" />
              <div className="absolute -bottom-48 left-1/3 h-[38rem] w-[38rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(251,146,60,0.12),transparent_70%)] blur-3xl animate-pulse-glow animation-delay-2000 dark:bg-[radial-gradient(circle_at_center,rgba(251,146,60,0.10),transparent_70%)]" />
              <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(24,24,27,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(24,24,27,0.03)_1px,transparent_1px)] bg-[size:64px_64px] dark:bg-[linear-gradient(to_right,rgba(244,244,245,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(244,244,245,0.03)_1px,transparent_1px)]" />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.8),transparent_50%)] dark:bg-[radial-gradient(circle_at_top,rgba(9,9,11,0.5),transparent_50%)]" />
            </div>
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  )
}
