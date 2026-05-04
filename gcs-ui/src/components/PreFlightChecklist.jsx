/**
 * Pre-Flight Checklist Modal
 * KTR §8.2 — uçuş öncesi sistem doğrulama listesi.
 */
import { useEffect, useState } from 'react'
import { PI_HOST } from '../constants'

const CHECKS = [
  { id: 'server',    label: 'Pi sunucusu erişilebilir', endpoint: '/api/system' },
  { id: 'camera',    label: 'Kamera çalışıyor (frame akışı)', deriveFromStatus: (s) => (s.fps ?? 0) > 1 },
  { id: 'model',     label: 'YOLO modeli yüklendi', deriveFromStatus: (s) => Array.isArray(s.detections) },
  { id: 'fsm',       label: 'FSM IDLE durumunda', deriveFromStatus: (s) => s.fsm?.state === 'IDLE' },
  { id: 'kamikaze',  label: 'Kamikaze servisi hazır', deriveFromStatus: (s) => s.kamikaze?.state === 'idle' },
  { id: 'comp',      label: 'Mock yarışma sunucusu (9000)', endpoint: 'comp:/api/rakip_iha' },
]

export default function PreFlightChecklist({ data, onClose, onStart }) {
  const [results, setResults] = useState({})

  useEffect(() => {
    let mounted = true
    async function run() {
      const out = {}
      for (const c of CHECKS) {
        if (c.deriveFromStatus) {
          out[c.id] = c.deriveFromStatus(data) ? 'ok' : 'fail'
          continue
        }
        if (!c.endpoint) { out[c.id] = 'unknown'; continue }
        try {
          const url = c.endpoint.startsWith('comp:')
            ? `http://${PI_HOST}:9000${c.endpoint.replace('comp:', '')}`
            : `http://${PI_HOST}:8000${c.endpoint}`
          const r = await fetch(url, { signal: AbortSignal.timeout(2000) })
          out[c.id] = r.ok ? 'ok' : 'fail'
        } catch { out[c.id] = 'fail' }
      }
      if (mounted) setResults(out)
    }
    run()
    return () => { mounted = false }
  }, [data])

  const allOk = CHECKS.every((c) => results[c.id] === 'ok')

  return (
    <div className="param-panel-overlay" onClick={onClose}>
      <div className="checklist-modal" onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <span className="panel-title">UÇUŞ ÖNCESİ KONTROL LİSTESİ — KTR §8.2</span>
          <button onClick={onClose} className="param-btn">KAPAT</button>
        </div>

        <div className="checklist-body">
          {CHECKS.map((c) => {
            const r = results[c.id]
            const color = r === 'ok' ? '#00e676' : r === 'fail' ? '#ff5252' : '#5a7894'
            const icon = r === 'ok' ? '☑' : r === 'fail' ? '☒' : '○'
            return (
              <div key={c.id} className="checklist-row" style={{ color }}>
                <span style={{ fontSize: 18, width: 24 }}>{icon}</span>
                <span style={{ flex: 1 }}>{c.label}</span>
                <span style={{ fontSize: 10, opacity: 0.7 }}>
                  {r === 'ok' ? 'OK' : r === 'fail' ? 'BAŞARISIZ' : 'KONTROL EDİLİYOR...'}
                </span>
              </div>
            )
          })}
        </div>

        <div className="checklist-footer">
          <button
            disabled={!allOk}
            onClick={() => { onStart?.(); onClose() }}
            className={`param-btn ${allOk ? 'ok' : ''}`}
            style={{ opacity: allOk ? 1 : 0.4, cursor: allOk ? 'pointer' : 'not-allowed' }}
          >
            {allOk ? 'GÖREVE BAŞLA →' : 'KONTROLLER TAMAMLANSIN'}
          </button>
        </div>
      </div>
    </div>
  )
}
