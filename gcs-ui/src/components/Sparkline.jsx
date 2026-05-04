/**
 * Hafif sparkline grafiği — tarihçeye dayalı.
 */
import { useEffect, useRef } from 'react'

export default function Sparkline({ values = [], color = '#00b4ff', max, min, height = 30, label, value, suffix }) {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    const w = canvas.offsetWidth, h = canvas.offsetHeight
    canvas.width = w * dpr; canvas.height = h * dpr
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, w, h)

    if (values.length < 2) return
    const lo = min ?? Math.min(...values)
    const hi = max ?? Math.max(...values)
    const span = Math.max(0.0001, hi - lo)
    const dx = w / (values.length - 1)

    ctx.strokeStyle = color
    ctx.lineWidth = 1.4
    ctx.beginPath()
    values.forEach((v, i) => {
      const x = i * dx
      const y = h - ((v - lo) / span) * (h - 4) - 2
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    })
    ctx.stroke()

    // Fill
    const grad = ctx.createLinearGradient(0, 0, 0, h)
    grad.addColorStop(0, color + '55')
    grad.addColorStop(1, color + '00')
    ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath()
    ctx.fillStyle = grad
    ctx.fill()
  }, [values, color, max, min])

  return (
    <div className="sparkline-wrap" style={{ height }}>
      {label && (
        <div className="sparkline-header">
          <span className="sparkline-label">{label}</span>
          {value !== undefined && (
            <span className="sparkline-value" style={{ color }}>{value}{suffix}</span>
          )}
        </div>
      )}
      <canvas ref={ref} className="sparkline-canvas" />
    </div>
  )
}
