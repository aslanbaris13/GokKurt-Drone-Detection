import { useRef, useEffect } from 'react'
import { STREAM_URL } from '../constants'

// ── Simülasyon canvas çizimi (server offline) ────────────────────────────────
function drawAirView(ctx, W, H, f, d) {
  const t = f / 60
  const sky = ctx.createLinearGradient(0, 0, 0, H * 0.62)
  sky.addColorStop(0, '#04091a'); sky.addColorStop(1, '#0c1a30')
  ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H * 0.62)
  const gnd = ctx.createLinearGradient(0, H * 0.62, 0, H)
  gnd.addColorStop(0, '#4a3010'); gnd.addColorStop(0.25, '#351f08'); gnd.addColorStop(1, '#160b02')
  ctx.fillStyle = gnd; ctx.fillRect(0, H * 0.62, W, H * 0.38)
  ctx.strokeStyle = 'rgba(160,110,50,0.5)'; ctx.lineWidth = 1
  ctx.beginPath(); ctx.moveTo(0, H * 0.62); ctx.lineTo(W, H * 0.62); ctx.stroke()
  ctx.fillStyle = 'rgba(0,0,0,0.07)'
  for (let y = 0; y < H; y += 3) ctx.fillRect(0, y, W, 1)
  const vig = ctx.createRadialGradient(W/2,H/2,H*0.25,W/2,H/2,H*0.82)
  vig.addColorStop(0,'rgba(0,0,0,0)'); vig.addColorStop(1,'rgba(0,0,0,0.45)')
  ctx.fillStyle = vig; ctx.fillRect(0,0,W,H)
  const tX = W*0.43+Math.sin(t*0.5)*18+Math.sin(t*0.85)*7
  const tY = H*0.37+Math.sin(t*0.42)*10+Math.cos(t*0.63)*5
  ctx.fillStyle='rgba(190,200,210,0.85)'
  ctx.beginPath(); ctx.ellipse(tX,tY,13,3,0,0,Math.PI*2); ctx.fill()
  ctx.beginPath(); ctx.moveTo(tX-5,tY-1); ctx.lineTo(tX-24,tY+3); ctx.lineTo(tX-22,tY-2); ctx.closePath(); ctx.fill()
  ctx.beginPath(); ctx.moveTo(tX+5,tY-1); ctx.lineTo(tX+24,tY+3); ctx.lineTo(tX+22,tY-2); ctx.closePath(); ctx.fill()
  ctx.beginPath(); ctx.moveTo(tX+11,tY); ctx.lineTo(tX+18,tY-7); ctx.lineTo(tX+18,tY); ctx.closePath(); ctx.fill()
  const bW=104+Math.sin(t*0.28)*9, bH=76+Math.cos(t*0.23)*6
  const bx=tX-bW/2, by=tY-bH/2
  const boxColor=d.confidence>0.9?'#00e676':'#ffb300'
  ctx.strokeStyle=boxColor; ctx.lineWidth=1.5; ctx.strokeRect(bx,by,bW,bH)
  const cs=14; ctx.lineWidth=2.5
  ;[[bx,by,cs,cs],[bx+bW,by,-cs,cs],[bx,by+bH,cs,-cs],[bx+bW,by+bH,-cs,-cs]]
    .forEach(([px,py,dx,dy])=>{ctx.beginPath();ctx.moveTo(px+dx,py);ctx.lineTo(px,py);ctx.lineTo(px,py+dy);ctx.stroke()})
  ctx.fillStyle=boxColor; ctx.font='bold 10px Courier New'; ctx.textAlign='left'
  ctx.fillText(`ID:0  DÜŞMAN İHA  ${(d.confidence*100).toFixed(1)}%`,bx,by-14)

  // Kilitlenme dörtgeni (KTR §6) — merkezde %6 alan
  const side = Math.sqrt(0.06) * Math.min(W, H)
  ctx.strokeStyle = 'rgba(0,180,255,0.45)'; ctx.lineWidth = 1; ctx.setLineDash([5, 4])
  ctx.strokeRect(W/2 - side/2, H/2 - side/2, side, side); ctx.setLineDash([])

  ctx.textAlign='left'; ctx.fillStyle='rgba(0,180,255,0.85)'; ctx.font='10px Courier New'
  ctx.fillText(new Date().toISOString().replace('T',' ').slice(0,19)+' UTC',8,18)
  ctx.fillText('SİMÜLASYON MODU — sunucu yok',8,31)
  ctx.fillText('MDL: YOLOv26n (mock)',8,44)

  // Hedef seçim skoru simülasyonda da göster
  const score = d.targetScore ?? 0
  const scoreCol = score >= 70 ? '#00e676' : score >= 40 ? '#ffb300' : '#ff5252'
  ctx.textAlign='right'; ctx.fillStyle=scoreCol; ctx.font='bold 10px Courier New'
  ctx.fillText(`SKOR: ${score.toFixed(0)}/100`, W - 8, 18)
  ctx.textAlign='left'
}

// ── Canlı modda overlay (Pi'den gelen JPEG üzerine bbox çizimi) ──────────────
function drawLiveOverlay(ctx, W, H, data) {
  // Kilitlenme dörtgeni — KTR §6
  const threshold = data.tracker?.lock_threshold ?? 0.06
  const side = Math.sqrt(threshold) * Math.min(W, H)
  ctx.strokeStyle = 'rgba(80, 180, 255, 0.55)'
  ctx.lineWidth = 1
  ctx.setLineDash([5, 4])
  ctx.strokeRect(W/2 - side/2, H/2 - side/2, side, side)
  ctx.setLineDash([])
  ctx.fillStyle = 'rgba(80, 180, 255, 0.6)'
  ctx.font = '9px Courier New'
  ctx.fillText('KİLİT DÖRTGENİ %6', W/2 - side/2, H/2 - side/2 - 3)

  // Crosshair
  ctx.strokeStyle = 'rgba(80, 180, 255, 0.25)'; ctx.lineWidth = 0.5
  ctx.beginPath(); ctx.moveTo(0, H/2); ctx.lineTo(W, H/2); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(W/2, 0); ctx.lineTo(W/2, H); ctx.stroke()

  // Bbox
  const fw = data.frameSize?.w || W, fh = data.frameSize?.h || H
  const sx = W / fw, sy = H / fh
  const locked = data.tracker?.locked
  const detections = data.detections || []
  detections.forEach((d, i) => {
    const [x1, y1, x2, y2] = d.bbox
    const bx = x1 * sx, by = y1 * sy, bw = (x2 - x1) * sx, bh = (y2 - y1) * sy
    const color = locked ? '#ff5252' : (d.confidence > 0.85 ? '#00e676' : '#ffb300')
    ctx.strokeStyle = color
    ctx.lineWidth = locked ? 2.5 : 1.5
    ctx.strokeRect(bx, by, bw, bh)
    // köşe parantezleri
    const cs = 12
    ctx.lineWidth = 2.5
    ;[[bx,by,cs,cs],[bx+bw,by,-cs,cs],[bx,by+bh,cs,-cs],[bx+bw,by+bh,-cs,-cs]]
      .forEach(([px, py, dx, dy]) => {
        ctx.beginPath(); ctx.moveTo(px+dx, py); ctx.lineTo(px, py); ctx.lineTo(px, py+dy); ctx.stroke()
      })
    ctx.fillStyle = color; ctx.font = 'bold 11px Courier New'
    ctx.fillText(`ID:${i}  ${d.class.toUpperCase()}  ${(d.confidence*100).toFixed(1)}%`, bx, by - 5)
    // Hedef seçim skoru (her bbox altında mini bar)
    if (d.score != null) {
      const barW = bw, barH = 4
      const barX = bx, barY = by + bh + 3
      ctx.fillStyle = 'rgba(0,0,0,0.45)'
      ctx.fillRect(barX, barY, barW, barH)
      const scoreColor = d.score >= 70 ? '#00e676' : d.score >= 40 ? '#ffb300' : '#ff5252'
      ctx.fillStyle = scoreColor
      ctx.fillRect(barX, barY, barW * d.score / 100, barH)
      ctx.font = '9px Courier New'
      ctx.fillStyle = scoreColor
      ctx.fillText(`SKOR ${d.score.toFixed(0)}`, barX, barY + 14)
    }
  })

  // QR polygon
  if (data.qr?.polygon?.length) {
    ctx.strokeStyle = '#00e676'; ctx.lineWidth = 2
    ctx.beginPath()
    data.qr.polygon.forEach((p, i) => {
      const x = p[0] * sx, y = p[1] * sy
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    })
    ctx.closePath(); ctx.stroke()
    ctx.fillStyle = '#00e676'; ctx.font = 'bold 10px Courier New'
    const p0 = data.qr.polygon[0]
    ctx.fillText(`QR: ${data.qr.data.slice(0, 30)}`, p0[0] * sx, p0[1] * sy - 6)
  }

  // Lock progress flash
  if (locked) {
    const a = 0.55 + Math.sin(performance.now() / 130) * 0.45
    ctx.fillStyle = `rgba(255, 82, 82, ${a})`
    ctx.font = 'bold 16px Courier New'; ctx.textAlign = 'center'
    ctx.fillText('◆ KİLİT AKTİF ◆', W/2, 28)
    ctx.textAlign = 'left'
  } else if (data.tracker?.criterion_met) {
    const pct = Math.round((data.tracker.lock_progress ?? 0) * 100)
    ctx.fillStyle = 'rgba(0, 200, 255, 0.95)'
    ctx.font = 'bold 12px Courier New'
    ctx.fillText(`KİLİT SAYACI: %${pct}  (${(data.tracker.lock_duration ?? 4).toFixed(1)}s)`, 8, 18)
  }

  // EKF tahmin göstergesi
  if (data.tracker?.predicted) {
    ctx.textAlign = 'center'
    ctx.fillStyle = 'rgba(255, 200, 60, 0.9)'
    ctx.font = 'bold 10px Courier New'
    ctx.fillText('▸ EKF TAHMİN', W / 2, H / 2 - (Math.sqrt(data.tracker.lock_threshold ?? 0.06) * Math.min(W, H)) / 2 - 12)
    ctx.textAlign = 'left'
  }

  // Top-right HUD
  ctx.textAlign = 'right'; ctx.font = '10px Courier New'
  ctx.fillStyle = 'rgba(122,215,255,0.85)'
  ctx.fillText(`FPS: ${data.fps?.toFixed?.(1) ?? '0'}`, W - 8, 18)
  ctx.fillText(`bbox: %${((data.tracker?.bbox_ratio ?? 0) * 100).toFixed(2)}`, W - 8, 32)
  ctx.fillText(`FSM: ${data.fsm?.state ?? 'IDLE'}`, W - 8, 46)
  // Hedef skoru top-right
  const score = data.targetScore ?? data.detections?.[0]?.score ?? 0
  const scoreCol = score >= 70 ? '#00e676' : score >= 40 ? '#ffb300' : '#ff5252'
  ctx.fillStyle = scoreCol
  ctx.fillText(`SKOR: ${score.toFixed(0)}/100`, W - 8, 60)
  ctx.textAlign = 'left'
}

// ── Ana bileşen ──────────────────────────────────────────────────────────────
export default function CameraPanel({ data }) {
  const canvasRef = useRef(null)
  const dataRef = useRef(data)
  const frameRef = useRef(0)
  const animRef = useRef(null)

  useEffect(() => { dataRef.current = data }, [data])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    function resize() {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }
    resize()
    const ro = new ResizeObserver(resize); ro.observe(canvas)

    function draw() {
      animRef.current = requestAnimationFrame(draw)
      frameRef.current++
      const d = dataRef.current
      const W = canvas.width, H = canvas.height
      if (!W || !H) return
      ctx.clearRect(0, 0, W, H)
      if (d.online) {
        drawLiveOverlay(ctx, W, H, d)
      } else {
        drawAirView(ctx, W, H, frameRef.current, d)
      }
    }
    draw()
    return () => { cancelAnimationFrame(animRef.current); ro.disconnect() }
  }, [])

  return (
    <div className="panel camera-panel">
      <div className="panel-header">
        <span className="panel-title">KAMERA GÖRÜNTÜSİ & NESNE TESPİTİ</span>
        <div className="panel-badges">
          <span className={`badge ${data.online ? 'green' : 'red'}`}>
            {data.online ? '● CANLI (Pi)' : '○ SİMÜLASYON'}
          </span>
          <span className="badge blue">YOLOv26n</span>
          {data.tracker?.locked && <span className="badge red">◆ KİLİT</span>}
          {data.qr && <span className="badge green">QR ✓</span>}
        </div>
      </div>

      <div className="camera-canvas" style={{ position: 'relative', overflow: 'hidden' }}>
        {data.online && (
          <img
            src={STREAM_URL}
            alt="Pi kamera akışı"
            style={{
              position: 'absolute', inset: 0,
              width: '100%', height: '100%',
              objectFit: 'contain', display: 'block',
              zIndex: 0,
            }}
          />
        )}
        <canvas
          ref={canvasRef}
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            zIndex: 1, pointerEvents: 'none',
          }}
        />
      </div>
    </div>
  )
}
