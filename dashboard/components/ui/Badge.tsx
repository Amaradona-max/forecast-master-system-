"use client"

import { type ReactNode } from "react"

type BadgeVariant = "success" | "warning" | "info" | "danger" | "default"
type BadgeSize = "sm" | "md" | "lg"

type BadgeProps = {
  children: ReactNode
  variant?: BadgeVariant
  size?: BadgeSize
  icon?: ReactNode
  pulse?: boolean
  className?: string
}

const variantClasses: Record<BadgeVariant, string> = {
  success: "badge-success",
  warning: "badge-warning",
  info: "badge-info",
  danger: "badge-danger",
  default: "border-neutral-300 bg-neutral-100 text-neutral-700 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text-secondary"
}

const sizeClasses: Record<BadgeSize, string> = {
  sm: "px-2 py-0.5 text-[10px]",
  md: "px-3 py-1 text-xs",
  lg: "px-4 py-1.5 text-sm"
}

export function Badge({
  children,
  variant = "default",
  size = "md",
  icon,
  pulse = false,
  className = ""
}: BadgeProps) {
  const baseClasses = "badge-base"
  const variantClass = variantClasses[variant]
  const sizeClass = sizeClasses[size]
  const pulseClass = pulse ? "animate-pulse-glow" : ""

  return (
    <span className={`${baseClasses} ${variantClass} ${sizeClass} ${pulseClass} ${className}`}>
      {icon && <span className="inline-flex items-center">{icon}</span>}
      {children}
    </span>
  )
}
