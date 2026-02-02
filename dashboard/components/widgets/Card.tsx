import { PropsWithChildren } from "react"

export function Card({ children, className }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={[
        "card-wow animate-fade-in",
        className ?? ""
      ].join(" ")}
    >
      {children}
    </div>
  )
}
