/**
 * Sağ alt köşede scroll'lu sistem event log'u.
 * Mission Planner'ın MAVLink Inspector benzeri.
 */
import { useEffect, useRef, useState } from 'react'

const LEVEL_COLORS = {
  info:    '#7ad7ff',
  success: '#00e676',
  warning: '#ffb300',
  error:   '#ff5252',
}

export default function EventLogPanel({ events = [] }) {
  const [filter, setFilter] = useState('all')
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events])

  const filtered = filter === 'all'
    ? events
    : events.filter((e) => e.level === filter || e.source === filter)

  return (
    <div className="panel event-log-panel">
      <div className="panel-header">
        <span className="panel-title">SİSTEM OLAYLARI</span>
        <div className="panel-badges">
          {['all', 'info', 'warning', 'error', 'success'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`filter-btn ${filter === f ? 'active' : ''}`}
              style={{
                background: filter === f ? '#0c2440' : 'transparent',
                color: filter === f ? '#7ad7ff' : '#5a7894',
                border: '1px solid #1e3a5a',
                padding: '2px 7px', fontSize: 9,
                fontFamily: 'Courier New', cursor: 'pointer',
                marginLeft: 2, textTransform: 'uppercase',
              }}
            >{f}</button>
          ))}
        </div>
      </div>
      <div ref={scrollRef} className="event-log-list">
        {filtered.length === 0 && (
          <div className="event-empty">Olay yok</div>
        )}
        {filtered.map((e, i) => (
          <div key={i} className="event-row" style={{ borderLeft: `3px solid ${LEVEL_COLORS[e.level] || '#5a7894'}` }}>
            <span className="event-ts">{formatTs(e.ts)}</span>
            <span className="event-source" style={{ color: LEVEL_COLORS[e.level] || '#5a7894' }}>
              {e.source?.toUpperCase()}
            </span>
            <span className="event-msg">{e.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function formatTs(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('tr-TR', { hour12: false }) + '.' +
    String(d.getMilliseconds()).padStart(3, '0')
}
