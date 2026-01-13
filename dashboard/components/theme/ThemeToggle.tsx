"use client"

import { useEffect, useState } from "react"

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    setIsDark(document.documentElement.classList.contains("dark"))
  }, [])

  return (
    <button
      className="rounded-xl border border-zinc-200/70 bg-white/70 px-3 py-2 text-sm shadow-sm backdrop-blur-md hover:bg-white/85 dark:border-zinc-800/70 dark:bg-zinc-900/55 dark:hover:bg-zinc-900/70"
      onClick={() => {
        const next = !isDark
        document.documentElement.classList.toggle("dark", next)
        window.localStorage.setItem("theme", next ? "dark" : "light")
        setIsDark(next)
      }}
      type="button"
    >
      {isDark ? "Chiaro" : "Scuro"}
    </button>
  )
}
