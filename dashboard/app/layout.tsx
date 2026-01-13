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
      <body className="min-h-screen bg-zinc-50 text-zinc-900 antialiased dark:bg-zinc-950 dark:text-zinc-50">
        <ThemeProvider>
          <div className="relative min-h-screen">
            <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
              <div className="absolute -left-32 -top-40 h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.28),transparent_60%)] blur-2xl dark:bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.20),transparent_60%)]" />
              <div className="absolute -right-32 -top-32 h-[30rem] w-[30rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.22),transparent_60%)] blur-2xl dark:bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.16),transparent_60%)]" />
              <div className="absolute -bottom-48 left-1/3 h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(168,85,247,0.18),transparent_60%)] blur-2xl dark:bg-[radial-gradient(circle_at_center,rgba(168,85,247,0.14),transparent_60%)]" />
              <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(24,24,27,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(24,24,27,0.06)_1px,transparent_1px)] bg-[size:32px_32px] dark:bg-[linear-gradient(to_right,rgba(244,244,245,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(244,244,245,0.06)_1px,transparent_1px)]" />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.66),transparent_55%)] dark:bg-[radial-gradient(circle_at_top,rgba(9,9,11,0.44),transparent_55%)]" />
            </div>
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  )
}
