/**
 * Mission Planner CONFIG/TUNING tarzı runtime parametre tablosu.
 * GET /api/params'dan oku, PATCH /api/params/{key} ile güncelle.
 */
import { useEffect, useMemo, useState } from 'react'
import { PI_HOST } from '../constants'

const API = `http://${PI_HOST}:8000/api/params`

const PARAM_GROUPS = {
  YOLO_:   { name: 'TESPİT', color: '#00b4ff' },
  CAMERA_: { name: 'KAMERA', color: '#7ad7ff' },
  PAN_:    { name: 'SERVO',  color: '#ffb300' },
  TILT_:   { name: 'SERVO',  color: '#ffb300' },
  LED_:    { name: 'UYARI',  color: '#ffb300' },
  BUZZER_: { name: 'UYARI',  color: '#ffb300' },
  LOCK_:   { name: 'KİLİT',  color: '#00e676' },
  QR_:     { name: 'QR',     color: '#00e676' },
  FSM_:    { name: 'FSM',    color: '#b388ff' },
  COMP_:   { name: 'YARIŞMA SUNUCUSU', color: '#f06292' },
  LOG_:    { name: 'LOGLAMA', color: '#5a7894' },
  EVENT_:  { name: 'LOGLAMA', color: '#5a7894' },
  SIM:     { name: 'SİSTEM', color: '#ff5252' },
}

function paramGroup(key) {
  for (const prefix of Object.keys(PARAM_GROUPS)) {
    if (key.startsWith(prefix)) return PARAM_GROUPS[prefix]
  }
  return { name: 'DİĞER', color: '#5a7894' }
}

export default function ParameterPanel({ onClose }) {
  const [params, setParams] = useState({})
  const [search, setSearch] = useState('')
  const [edits, setEdits]   = useState({})
  const [error, setError]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(API)
      .then((r) => r.json())
      .then((p) => { setParams(p); setLoading(false) })
      .catch((e) => { setError(String(e)); setLoading(false) })
  }, [])

  const filtered = useMemo(() => {
    const s = search.toLowerCase()
    return Object.entries(params)
      .filter(([k]) => k.toLowerCase().includes(s))
      .sort(([a], [b]) => a.localeCompare(b))
  }, [params, search])

  async function commit(key, value) {
    try {
      const r = await fetch(`${API}/${key}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      })
      const j = await r.json()
      setParams((p) => ({ ...p, [key]: j.value }))
      setEdits((e) => { const c = { ...e }; delete c[key]; return c })
    } catch (e) { setError(String(e)) }
  }

  return (
    <div className="param-panel-overlay" onClick={onClose}>
      <div className="param-panel" onClick={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <span className="panel-title">PARAMETRE LİSTESİ — Mission Planner Tarzı</span>
          <div className="panel-badges">
            <span className="badge blue">{Object.keys(params).length} param</span>
            <button onClick={onClose} style={{
              background: '#1e3a5a', color: '#7ad7ff', border: 'none',
              padding: '2px 10px', cursor: 'pointer', marginLeft: 8,
              fontFamily: 'Courier New',
            }}>KAPAT</button>
          </div>
        </div>

        <input
          type="text"
          placeholder="ARA: YOLO_, LOCK_, SERVO_, FSM_..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="param-search"
        />

        {loading && <div className="param-msg">Yükleniyor...</div>}
        {error && <div className="param-msg error">Hata: {error}</div>}

        <div className="param-table-wrap">
          <table className="param-table">
            <thead>
              <tr>
                <th>ANAHTAR</th>
                <th>GRUP</th>
                <th>DEĞER</th>
                <th>YENİ</th>
                <th>İŞLEM</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(([key, val]) => {
                const grp = paramGroup(key)
                const editing = edits[key] !== undefined
                const editVal = editing ? edits[key] : String(val)
                const dirty = editing && editVal !== String(val)
                return (
                  <tr key={key} style={{ borderBottom: '1px solid #11253c' }}>
                    <td className="param-key">{key}</td>
                    <td>
                      <span style={{
                        color: grp.color, fontSize: 9,
                        padding: '1px 6px', border: `1px solid ${grp.color}`,
                        borderRadius: 2,
                      }}>{grp.name}</span>
                    </td>
                    <td className="param-val">{String(val)}</td>
                    <td>
                      <input
                        type="text"
                        value={editVal}
                        onChange={(e) => setEdits((p) => ({ ...p, [key]: e.target.value }))}
                        className="param-input"
                        style={{ borderColor: dirty ? '#ffb300' : '#11253c' }}
                      />
                    </td>
                    <td>
                      {dirty ? (
                        <button onClick={() => {
                          let v = edits[key]
                          if (typeof val === 'number') v = Number(v)
                          if (typeof val === 'boolean') v = String(v).toLowerCase() === 'true'
                          commit(key, v)
                        }} className="param-btn ok">UYGULA</button>
                      ) : (
                        <span style={{ color: '#5a7894', fontSize: 9 }}>—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
