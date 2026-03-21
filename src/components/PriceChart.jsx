import React, { useMemo } from 'react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  ComposedChart,
  ReferenceLine,
} from 'recharts'
import { formatPrice, formatShortDate } from '../utils/formatters'
import { linearRegression } from '../utils/statistics'

const TYPE_COLORS = {
  House: '#4f6ef7',
  Unit: '#34d399',
  Townhouse: '#fbbf24',
  Land: '#a78bfa',
}

function CustomDot({ cx, cy, fill, payload }) {
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill={fill}
      fillOpacity={0.75}
      stroke={fill}
      strokeWidth={1.5}
      strokeOpacity={0.4}
    />
  )
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null

  return (
    <div style={{
      background: '#1a1d27',
      border: '1px solid #2e3350',
      borderRadius: 6,
      padding: '10px 14px',
      fontSize: 12,
    }}>
      <div style={{ color: '#e8eaf0', fontWeight: 600, marginBottom: 4 }}>
        {d.address}
      </div>
      <div style={{ color: TYPE_COLORS[d.type] || '#4f6ef7' }}>{d.type}</div>
      <div style={{ color: '#e8eaf0', fontSize: 14, fontWeight: 700, marginTop: 4 }}>
        {formatPrice(d.price)}
      </div>
      <div style={{ color: '#9aa0b8', marginTop: 2 }}>{formatShortDate(d.date)}</div>
      {d.area > 0 && <div style={{ color: '#9aa0b8' }}>{d.area.toLocaleString()} m²</div>}
    </div>
  )
}

export default function PriceChart({ properties, filters }) {
  // Convert dates to numeric (days since start)
  const chartData = useMemo(() => {
    if (!properties.length) return { points: [], trendLines: {}, dateRange: [null, null] }

    const sorted = [...properties].sort((a, b) => new Date(a.date) - new Date(b.date))
    const minDate = new Date(sorted[0].date).getTime()
    const maxDate = new Date(sorted[sorted.length - 1].date).getTime()
    const range = maxDate - minDate || 1

    const points = sorted.map(p => ({
      ...p,
      xNum: (new Date(p.date).getTime() - minDate) / (1000 * 60 * 60 * 24), // days
      timestamp: new Date(p.date).getTime(),
    }))

    // Trend line per visible type
    const trendLines = {}
    filters.types.forEach(type => {
      const typePoints = points.filter(p => p.type === type)
      if (typePoints.length < 2) return
      const xs = typePoints.map(p => p.xNum)
      const ys = typePoints.map(p => p.price)
      const { slope, intercept } = linearRegression(xs, ys)
      const x0 = Math.min(...xs)
      const x1 = Math.max(...xs)
      trendLines[type] = [
        { x: x0, y: slope * x0 + intercept },
        { x: x1, y: slope * x1 + intercept },
      ]
    })

    // Date ticks: split into 6 evenly spaced ticks
    const totalDays = (maxDate - minDate) / (1000 * 60 * 60 * 24)
    const tickInterval = totalDays / 5
    const ticks = Array.from({ length: 6 }, (_, i) => Math.round(i * tickInterval))

    return {
      points,
      trendLines,
      ticks,
      minDate,
      dateFormatter: (dayNum) => {
        const d = new Date(minDate + dayNum * 24 * 60 * 60 * 1000)
        return d.toLocaleDateString('en-AU', { month: 'short', year: '2-digit' })
      },
    }
  }, [properties, filters.types])

  if (!properties.length) {
    return (
      <div className="chart-empty">
        <p>No transactions found for this period.</p>
        <p style={{ fontSize: 11, color: '#555', marginTop: 4 }}>
          Try adjusting filters or selecting a different time period.
        </p>
      </div>
    )
  }

  // Group by type for multiple scatter series
  const groupedByType = useMemo(() => {
    const groups = {}
    chartData.points?.forEach(p => {
      if (!groups[p.type]) groups[p.type] = []
      groups[p.type].push(p)
    })
    return groups
  }, [chartData.points])

  return (
    <div className="chart-wrapper">
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart margin={{ top: 8, right: 12, bottom: 20, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2235" vertical={false} />

          <XAxis
            type="number"
            dataKey="x"
            domain={['auto', 'auto']}
            ticks={chartData.ticks}
            tickFormatter={chartData.dateFormatter}
            tick={{ fill: '#555', fontSize: 11 }}
            axisLine={{ stroke: '#2e3350' }}
            tickLine={false}
            label={{ value: '', position: 'insideBottom' }}
          />

          <YAxis
            type="number"
            dataKey="y"
            tickFormatter={v => `$${(v / 1000000).toFixed(1)}M`}
            tick={{ fill: '#555', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={52}
          />

          <Tooltip content={<CustomTooltip />} />

          {/* Scatter points per type */}
          {filters.types.map(type => {
            const pts = groupedByType[type] || []
            return pts.length > 0 ? (
              <Scatter
                key={type}
                name={type}
                data={pts.map(p => ({ ...p, x: p.xNum, y: p.price }))}
                fill={TYPE_COLORS[type] || '#4f6ef7'}
                shape={<CustomDot fill={TYPE_COLORS[type] || '#4f6ef7'} />}
              />
            ) : null
          })}

          {/* Trend lines per type */}
          {filters.types.map(type => {
            const tl = chartData.trendLines?.[type]
            if (!tl) return null
            return (
              <Line
                key={`trend-${type}`}
                data={tl}
                dataKey="y"
                dot={false}
                activeDot={false}
                stroke={TYPE_COLORS[type] || '#4f6ef7'}
                strokeWidth={2}
                strokeDasharray="6 3"
                strokeOpacity={0.8}
                type="linear"
              />
            )
          })}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="chart-legend">
        {filters.types.map(type => {
          const count = groupedByType[type]?.length || 0
          return count > 0 ? (
            <div key={type} className="chart-legend-item">
              <span
                className="chart-legend-dot"
                style={{ background: TYPE_COLORS[type] }}
              />
              <span>{type}</span>
              <span className="chart-legend-count">{count}</span>
            </div>
          ) : null
        })}
        <div className="chart-legend-item trend-hint">
          <span className="chart-legend-dashed" style={{ borderColor: '#9aa0b8' }} />
          <span style={{ color: '#555' }}>Trend</span>
        </div>
      </div>
    </div>
  )
}
