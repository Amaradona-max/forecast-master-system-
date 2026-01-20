"use client"

import React from "react"
import { FixedSizeList, type ListChildComponentProps } from "react-window"

export function VirtualList<T>({
  items,
  height,
  itemSize,
  width = "100%",
  overscanCount = 6,
  renderRow,
  className
}: {
  items: T[]
  height: number
  itemSize: number
  width?: number | string
  overscanCount?: number
  className?: string
  renderRow: (item: T, index: number) => React.ReactNode
}) {
  const Row = ({ index, style }: ListChildComponentProps) => (
    <div style={style} className={className}>
      {renderRow(items[index] as T, index)}
    </div>
  )

  return (
    <FixedSizeList height={height} itemCount={items.length} itemSize={itemSize} width={width} overscanCount={overscanCount}>
      {Row}
    </FixedSizeList>
  )
}
