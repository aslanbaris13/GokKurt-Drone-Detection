import { FSM_STATES } from '../constants'

function MetricBar({ label, value, pct, color }) {
  return (
    <div className="metric-item">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color }}>{value}</div>
      {pct !== undefined && (
        <div className="metric-bar-bg">
          <div className="metric-bar-fill" style={{ width: `${Math.min(100, Math.max(0, pct))}%`, background: color }} />
        </div>
      )}
    </div>
  )
}

function SignalBars({ rssi }) {
  const strength = rssi > -55 ? 4 : rssi > -65 ? 3 : rssi > -75 ? 2 : 1
  return (
    <div className="signal-bars">
      {[1, 2, 3, 4].map(n => (
        <div
          key={n}
          className="signal-bar"
          style={{
            height: `${n * 4 + 4}px`,
            background: n <= strength ? '#00e676' : '#1e3a5a',
          }}
        />
      ))}
    </div>
  )
}

function PacketBadge({ state }) {
  const map = {
    idle:    { color: '#5a7894', text: '○ HAZIR' },
    sending: { color: '#ffb300', text: '⟳ GÖNDERİLİYOR' },
    ack:     { color: '#00e676', text: '✓ ACK' },
    failed:  { color: '#ff5252', text: '✗ BAŞARISIZ' },
  }
  const v = map[state] || map.idle
  return <span className="packet-badge" style={{ color: v.color, borderColor: v.color }}>{v.text}</span>
}

export default function BottomBar({ data, onOpenParams, onOpenChecklist }) {
  const batColor = data.battery > 50 ? '#00e676' : data.battery > 25 ? '#ffb300' : '#f44336'
  const cpuTempColor = data.cpuTemp != null && data.cpuTemp < 60 ? '#00e676' : '#ffb300'
  const lockOk = data.lockSent === data.lockAck
  const kamState = data.kamikaze?.state || 'idle'
  const kamAttempts = data.kamikaze?.attempts || 0
  const kamMaxAttempts = data.kamikaze?.max_attempts || 3

  const fsmIdx = data.fsmStateIdx
  const fsmState = FSM_STATES[fsmIdx] || data.fsm?.state || 'IDLE'
  const isAbort = data.fsm?.state === 'ABORT'

  return (
    <div className="bottom-bar">

      {/* FSM State strip */}
      <div className="bottom-section fsm-section">
        <div className="section-label">FSM DURUMU</div>
        <div className="fsm-row">
          {FSM_STATES.map((s, i) => (
            <div key={s} className="fsm-chip-wrap">
              <div className={`fsm-chip ${i === fsmIdx ? 'active' : i < fsmIdx ? 'done' : ''}`}>
                {s}
              </div>
              {i < FSM_STATES.length - 1 && <span className="fsm-arrow">›</span>}
            </div>
          ))}
          {isAbort && (
            <div className="fsm-chip-wrap">
              <span className="fsm-arrow">›</span>
              <div className="fsm-chip" style={{ borderColor: '#ff5252', color: '#ff5252' }}>ABORT</div>
            </div>
          )}
        </div>
        <div className="fsm-timer">
          Aktif: <span className="fsm-timer-val">{fsmState}</span>
          &nbsp;— {data.fsmTime?.toFixed?.(1) ?? '0.0'} s
          {data.fsm?.abort_reason && (
            <span style={{ color: '#ff5252', marginLeft: 12 }}>⚠ {data.fsm.abort_reason}</span>
          )}
        </div>

        <div style={{ marginTop: 6, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {onOpenChecklist && (
            <button onClick={onOpenChecklist} className="param-btn">PRE-FLIGHT</button>
          )}
          {onOpenParams && (
            <button onClick={onOpenParams} className="param-btn">PARAMETRELER</button>
          )}
          {isAbort && (
            <button
              className="param-btn"
              style={{ borderColor: '#ff5252', color: '#ff5252', fontWeight: 'bold', animation: 'failsafePulse 1s infinite' }}
              onClick={() => {
                fetch(`http://${location.hostname}:8000/api/mission/reset`, { method: 'POST' })
                  .catch(() => {})
              }}
            >
              ↺ SİSTEM RESET
            </button>
          )}
        </div>
      </div>

      {/* Telemetry */}
      <div className="bottom-section telem-section">
        <div className="section-label">TELEMETRİ</div>
        <div className="telem-grid">
          {[
            { l: 'İRTİFA', v: `${data.alt?.toFixed?.(1) ?? '—'} m` },
            { l: 'HIZ', v: `${data.speed?.toFixed?.(1) ?? '—'} m/s` },
            { l: 'HEADING', v: `${Math.round(data.heading ?? 0).toString().padStart(3, '0')}°` },
            { l: 'ROLL', v: `${data.roll?.toFixed?.(1) ?? '—'}°` },
            { l: 'PİTCH', v: `${data.pitch?.toFixed?.(1) ?? '—'}°` },
            { l: 'GPS', v: '3D Fix' },
            { l: 'UYDU', v: data.satellites },
            { l: 'BBOX', v: `%${(data.bboxPct ?? 0).toFixed(2)}` },
          ].map(({ l, v }) => (
            <div key={l} className="telem-cell">
              <div className="telem-label">{l}</div>
              <div className="telem-val">{v}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Packet status */}
      <div className="bottom-section packet-section">
        <div className="section-label">PAKET DURUMU</div>
        <div className="packet-item">
          <span className="packet-label">Kilit Paketi</span>
          <span className="packet-count">{data.lockSent} / {data.lockAck} ACK</span>
          <span className={`packet-badge ${lockOk ? 'ok' : 'warn'}`}>{lockOk ? '✓ OK' : '! HATA'}</span>
        </div>
        <div className="packet-item">
          <span className="packet-label">Kamikaze Paketi</span>
          <span className="packet-count">
            {data.kamSent}/{data.kamAck} ACK
            {kamState === 'sending' && (
              <span style={{ color: '#ffb300', marginLeft: 6 }}>
                (deneme {kamAttempts}/{kamMaxAttempts})
              </span>
            )}
          </span>
          <PacketBadge state={kamState} />
        </div>
        {data.kamikaze?.last_error && (
          <div className="packet-item" style={{ marginTop: 4 }}>
            <span className="packet-label" style={{ color: '#ff5252', fontSize: 9 }}>
              Son hata: {data.kamikaze.last_error.slice(0, 50)}
            </span>
          </div>
        )}
        <div className="packet-item" style={{ marginTop: 4 }}>
          <span className="packet-label">MAVLink Kalite</span>
          <span className="packet-count" style={{ color: '#00e676' }}>%98</span>
          <span className="packet-badge ok">✓ OK</span>
        </div>
      </div>

      {/* System metrics */}
      <div className="bottom-section metrics-section">
        <div className="section-label">SİSTEM METRİKLERİ</div>
        <div className="metrics-grid">
          <MetricBar label="BATARYA" value={`${data.battery?.toFixed?.(0) ?? '—'}%`} pct={data.battery} color={batColor} />
          <div className="metric-item">
            <div className="metric-label">RSSI</div>
            <div className="metric-value" style={{ color: '#00b4ff' }}>{data.rssi} dBm</div>
            <SignalBars rssi={data.rssi} />
          </div>
          <MetricBar label="GPU ISI" value={`${data.gpuTemp?.toFixed?.(0) ?? '—'}°C`} color={cpuTempColor} />
          <MetricBar label="CPU ISI" value={`${data.cpuTemp?.toFixed?.(0) ?? '—'}°C`} color={cpuTempColor} />
          <MetricBar label="GPU/CPU" value={`${data.gpuUsage?.toFixed?.(0) ?? '—'}%`} pct={data.gpuUsage} color="#00b4ff" />
        </div>
      </div>

    </div>
  )
}
