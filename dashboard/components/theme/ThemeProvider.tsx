"use client"

import { useEffect, useState } from "react"

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const saved = window.localStorage.getItem("theme")
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches
    const theme = saved === "dark" || saved === "light" ? saved : prefersDark ? "dark" : "light"
    document.documentElement.classList.toggle("dark", theme === "dark")
    setReady(true)
  }, [])

  if (!ready) return <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950" />
  return <>{children}</>
}

