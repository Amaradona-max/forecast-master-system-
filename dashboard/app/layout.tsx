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
      <body className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 text-zinc-900 antialiased dark:from-[#0b1020] dark:via-[#0f172a] dark:to-[#111827] dark:text-zinc-50">
        <ThemeProvider>
          <div className="relative min-h-screen app-aurora">
            <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
              <div className="absolute -left-32 -top-40 h-[40rem] w-[40rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(0,186,164,0.18),transparent_70%)] blur-3xl animate-pulse-glow dark:bg-[radial-gradient(circle_at_center,rgba(59,130,246,0.18),transparent_70%)]" />
              <div className="absolute -right-32 -top-32 h-[36rem] w-[36rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(40,82,255,0.15),transparent_70%)] blur-3xl animate-pulse-glow animation-delay-1000 dark:bg-[radial-gradient(circle_at_center,rgba(99,102,241,0.18),transparent_70%)]" />
              <div className="absolute -bottom-48 left-1/3 h-[38rem] w-[38rem] rounded-full bg-[radial-gradient(circle_at_center,rgba(14,165,233,0.12),transparent_70%)] blur-3xl animate-pulse-glow animation-delay-2000 dark:bg-[radial-gradient(circle_at_center,rgba(14,165,233,0.14),transparent_70%)]" />
              <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(15,23,42,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(15,23,42,0.03)_1px,transparent_1px)] bg-[size:64px_64px] dark:bg-[linear-gradient(to_right,rgba(59,130,246,0.08)_1px,transparent_1px),linear-gradient(to_bottom,rgba(59,130,246,0.08)_1px,transparent_1px)]" />
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.75),transparent_55%)] dark:bg-[radial-gradient(circle_at_top,rgba(15,23,42,0.65),transparent_55%)]" />
            </div>
            {children}
          </div>
        </ThemeProvider>
      </body>
    </html>
  )
}
