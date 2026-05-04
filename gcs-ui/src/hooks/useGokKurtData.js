/**
 * GökKurt birleşik veri kaynağı.
 *
 * Pi sunucusu erişilebilirse server'dan gelen gerçek verileri,
 * erişilemezse şartnameye uygun simülasyonu döndürür.
 */
import { useEffect, useRef, useState } from 'react'
import { WS_URL } from '../constants'

const FSM_STATES = ['IDLE', 'INTIKAL', 'DALIS', 'KILIT', 'PAS_GEC', 'DONUS']
const FSM_DURATIONS = [4, 14, 8, 20, 6, 12]
const FSM_PARAMS = [
  { speedBase: 0,  altBase: 5,   pitchBase: 0,   rollBase: 0,  bboxBase: 2.0 },
  { speedBase: 17, altBase: 100, pitchBase: -2,  rollBase: 5,  bboxBase: 3.2 },
  { speedBase: 25, altBase: 65,  pitchBase: -26, rollBase: 8,  bboxBase: 4.8 },
  { speedBase: 17, altBase: 98,  pitchBase: -2,  rollBase: 3,  bboxBase: 6.4 },
  { speedBase: 27, altBase: 125, pitchBase: 14,  rollBase: 10, bboxBase: 3.0 },
  { speedBase: 18, altBase: 112, pitchBase: -1,  rollBase: -5, bboxBase: 2.5 },
]

const noise = (a) => (Math.random() - 0.5) * a
const lerp  = (a, b, t) => a + (b - a) * t

const INITIAL = {
  // Mevcut UI ile uyumlu
  lat: 40.9018, lon: 31.1795,
  alt: 98.0, speed: 17.0, heading: 127,
  roll: 2.8, pitch: -1.6,
  enemyLat: 40.9062, enemyLon: 31.1868,
  battery: 82.0, rssi: -61,
  gpuTemp: 54.2, cpuTemp: 47.8, gpuUsage: 76.4,
  fsmStateIdx: 3,
  fsmTime: 0,
  lockSent: 12, lockAck: 12,
  kamSent: 3, kamAck: 3,
  confidence: 0.924, bboxPct: 6.4,
  satellites: 12, mavlinkHz: 10,
  frame: 360,

  // Yeni alanlar
  online: false,           // server canlı mı?
  detections: [],          // [{bbox, confidence, class, score}]
  qr: null,                // {data, polygon, bbox}
  fps: 0,
  targetScore: 0,          // Hedef seçim skoru (0-100)
  tracker: { tracking: false, locked: false, lock_progress: 0,
             bbox_ratio: 0, criterion_met: false,
             lock_threshold: 0.06, lock_duration: 4.0 },
  fsm: { state: 'IDLE', state_index: 0, time_in_state: 0,
         abort_reason: null, recent_transitions: [] },
  kamikaze: { state: 'idle', attempts: 0, max_attempts: 3,
              last_packet: null, last_error: null, history: [] },
  telemetry: null,         // server'dan gelen sistem telemetri
  events: [],
  frameSize: { w: 640, h: 480 },
}

export function useGokKurtData() {
  const [data, setData] = useState(INITIAL)
  const tickRef = useRef(0)
  const wpProgRef = useRef(0)
  const wpIdxRef = useRef(0)
  const onlineRef = useRef(false)

  // ── WebSocket bağlantısı ─────────────────────────────────────────────────
  useEffect(() => {
    let ws, retry
    function connect() {
      try {
        ws = new WebSocket(WS_URL)
      } catch {
        retry = setTimeout(connect, 3000)
        return
      }

      ws.onopen = () => {
        onlineRef.current = true
        setData((d) => ({ ...d, online: true }))
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          setData((prev) => mergeLive(prev, msg))
        } catch {}
      }

      ws.onclose = () => {
        onlineRef.current = false
        setData((d) => ({ ...d, online: false }))
        retry = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws?.close()
    }

    connect()
    return () => { clearTimeout(retry); ws?.close() }
  }, [])

  // ── Simülasyon (online değilse) ───────────────────────────────────────────
  useEffect(() => {
    const id = setInterval(() => {
      if (onlineRef.current) return  // canlı bağlantı varsa simüle etme

      tickRef.current++
      const t = tickRef.current

      wpProgRef.current += 0.004
      if (wpProgRef.current >= 1) {
        wpProgRef.current = 0
        wpIdxRef.current++
      }

      const WAYPOINTS = [
        [40.9018, 31.1795], [40.9038, 31.1835], [40.9062, 31.1868],
        [40.9080, 31.1848], [40.9070, 31.1800], [40.9042, 31.1772],
      ]
      const fromIdx = wpIdxRef.current % WAYPOINTS.length
      const from = WAYPOINTS[fromIdx]
      const to = WAYPOINTS[(fromIdx + 1) % WAYPOINTS.length]
      const p = wpProgRef.current

      setData((prev) => {
        let newFsmStateIdx = prev.fsmStateIdx
        let newFsmTime = prev.fsmTime + 0.1
        if (newFsmTime >= FSM_DURATIONS[prev.fsmStateIdx]) {
          newFsmStateIdx = (prev.fsmStateIdx + 1) % FSM_STATES.length
          newFsmTime = 0
        }

        const params = FSM_PARAMS[newFsmStateIdx]
        const speed = params.speedBase + Math.sin(t * 0.04) * 1.2 + noise(0.2)
        const alt = params.altBase + Math.sin(t * 0.05) * 2.5 + noise(0.3)
        const pitch = params.pitchBase + Math.sin(t * 0.03) * 2.5 + noise(0.3)
        const roll = params.rollBase + Math.sin(t * 0.04) * 4 + noise(0.3)
        const bboxPct = newFsmStateIdx === 3
          ? 6.15 + Math.abs(Math.sin(t * 0.07)) * 0.55
          : params.bboxBase + Math.sin(t * 0.06) * 0.6
        const confidence = newFsmStateIdx === 3
          ? Math.max(0.91, Math.min(0.99, prev.confidence + noise(0.006)))
          : Math.max(0.78, Math.min(0.94, prev.confidence + noise(0.01)))

        const sendPacket = t % 10 === 0 && newFsmStateIdx === 3
        const lockSent = sendPacket ? prev.lockSent + 1 : prev.lockSent
        const lockAck = sendPacket ? prev.lockSent + 1 : prev.lockAck

        // Hedef seçim skoru simülasyonu
        const centerScore   = newFsmStateIdx === 3 ? 16 + noise(3) : 10 + noise(5)
        const ratioScore    = newFsmStateIdx === 3 ? 27 + noise(2) : 12 + noise(6)
        const sizeScore     = bboxPct >= 4.0 ? 10 : bboxPct / 4.0 * 10
        const simScore      = Math.max(0, Math.min(100,
          confidence * 40 + ratioScore + centerScore + sizeScore))

        return {
          ...prev,
          lat: lerp(from[0], to[0], p), lon: lerp(from[1], to[1], p),
          alt, speed,
          heading: ((127 + Math.sin(t * 0.025) * 18) % 360 + 360) % 360,
          roll, pitch,
          enemyLat: 40.9062 + Math.sin(t * 0.018) * 0.0018,
          enemyLon: 31.1868 + Math.cos(t * 0.018) * 0.0020,
          battery: Math.max(15, prev.battery - 0.0012),
          rssi: -61 + Math.round(noise(6)),
          gpuTemp: 54 + Math.sin(t * 0.012) * 3 + noise(0.4),
          cpuTemp: 48 + Math.sin(t * 0.009) * 2 + noise(0.3),
          gpuUsage: 76 + Math.sin(t * 0.06) * 9 + noise(1.5),
          fsmStateIdx: newFsmStateIdx, fsmTime: newFsmTime,
          lockSent, lockAck,
          confidence, bboxPct,
          targetScore: simScore,
          frame: prev.frame + 3,
          tracker: {
            ...prev.tracker,
            tracking: newFsmStateIdx > 0 && newFsmStateIdx < 5,
            locked: newFsmStateIdx === 3 && newFsmTime > 4,
            lock_progress: newFsmStateIdx === 3 ? Math.min(1, newFsmTime / 4) : 0,
            bbox_ratio: bboxPct / 100,
            criterion_met: bboxPct >= 6.0,
          },
          fsm: { state: FSM_STATES[newFsmStateIdx], state_index: newFsmStateIdx,
                 time_in_state: newFsmTime, abort_reason: null, recent_transitions: [] },
        }
      })
    }, 100)
    return () => clearInterval(id)
  }, [])

  return data
}

// ── Live veriyi mevcut UI alanlarına eşle ─────────────────────────────────────
function mergeLive(prev, msg) {
  const tracker = msg.tracker || prev.tracker
  const fsmIdx = msg.fsm?.state_index ?? prev.fsmStateIdx
  const fsmIdxClamped = fsmIdx >= 0 && fsmIdx < FSM_STATES.length ? fsmIdx : 0

  const tele = msg.telemetry || {}
  const kam = msg.kamikaze || prev.kamikaze
  const kamHistory = kam.history || []
  const kamSent = kamHistory.length
  const kamAck = kamHistory.filter((h) => h.result === 'ack').length

  return {
    ...prev,
    online: true,
    detections: msg.detections || [],
    qr: msg.qr || null,
    fps: msg.fps ?? 0,
    tracker,
    fsm: msg.fsm || prev.fsm,
    fsmStateIdx: fsmIdxClamped,
    fsmTime: msg.fsm?.time_in_state ?? prev.fsmTime,
    kamikaze: kam,
    kamSent, kamAck,
    telemetry: tele,
    events: msg.events || prev.events,
    frameSize: msg.frame || prev.frameSize,

    // Telemetry → eski alanlar (BottomBar uyumu)
    battery: tele.battery_pct ?? prev.battery,
    cpuTemp: tele.cpu_temp_c ?? prev.cpuTemp,
    gpuTemp: tele.cpu_temp_c ?? prev.gpuTemp,   // Pi'de GPU sensörü ayrı yok
    gpuUsage: tele.cpu_pct ?? prev.gpuUsage,
    rssi: tele.wifi_rssi ?? prev.rssi,

    // Tracker → eski alanlar
    bboxPct: (tracker.bbox_ratio ?? 0) * 100,
    confidence: msg.detections?.[0]?.confidence ?? prev.confidence,
    targetScore: msg.target_score ?? msg.detections?.[0]?.score ?? prev.targetScore ?? 0,
  }
}
