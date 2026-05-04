/**
 * Sağ alt köşe sistem sağlığı (KTR §6).
 * batarya, RSSI, CPU/GPU sıcaklık, GPU kullanım.
 */
export default function SystemHealthStrip({ telemetry }) {
  if (!telemetry) {
    return (
      <div className="health-strip empty">
        <span style={{ color: '#5a7894', fontSize: 10 }}>SİSTEM TELEMETRİ — bağlantı bekleniyor</span>
      </div>
    )
  }

  const battery = telemetry.battery_pct
  const cpuTemp = telemetry.cpu_temp_c
  const cpuPct  = telemetry.cpu_pct
  const ramPct  = telemetry.ram_pct
  const rssi    = telemetry.wifi_rssi
  const throt   = telemetry.throttling

  const batColor = battery > 50 ? '#00e676' : battery > 25 ? '#ffb300' : '#ff5252'
  const tempColor = cpuTemp == null ? '#5a7894' : cpuTemp < 60 ? '#00e676' : cpuTemp < 75 ? '#ffb300' : '#ff5252'

  return (
    <div className="health-strip">
      <div className="health-cell" title="Pi/Mac platform">
        <div className="health-label">PLATFORM</div>
        <div className="health-val">{telemetry.platform || '—'}</div>
      </div>
      <div className="health-cell">
        <div className="health-label">BATARYA</div>
        <div className="health-val" style={{ color: batColor }}>
          {battery != null ? `${battery.toFixed(0)}%` : '—'}
        </div>
      </div>
      <div className="health-cell">
        <div className="health-label">CPU</div>
        <div className="health-val" style={{ color: tempColor }}>
          {cpuPct != null ? `${cpuPct.toFixed(0)}%` : '—'}
          {cpuTemp != null && <span style={{ marginLeft: 6, opacity: 0.7 }}>{cpuTemp.toFixed(0)}°C</span>}
        </div>
      </div>
      <div className="health-cell">
        <div className="health-label">RAM</div>
        <div className="health-val">
          {ramPct != null ? `${ramPct.toFixed(0)}%` : '—'}
          {telemetry.ram_used_mb != null && (
            <span style={{ marginLeft: 6, opacity: 0.6, fontSize: 10 }}>
              {Math.round(telemetry.ram_used_mb / 1024 * 10) / 10}/{Math.round(telemetry.ram_total_mb / 1024 * 10) / 10}GB
            </span>
          )}
        </div>
      </div>
      <div className="health-cell">
        <div className="health-label">RSSI</div>
        <div className="health-val" style={{ color: rssi != null && rssi > -65 ? '#00e676' : '#ffb300' }}>
          {rssi != null ? `${rssi} dBm` : '—'}
        </div>
      </div>
      <div className="health-cell">
        <div className="health-label">DİSK</div>
        <div className="health-val">
          {telemetry.disk_pct != null ? `${telemetry.disk_pct.toFixed(0)}%` : '—'}
        </div>
      </div>
      <div className="health-cell">
        <div className="health-label">UPTIME</div>
        <div className="health-val">
          {telemetry.uptime_s != null ? formatUptime(telemetry.uptime_s) : '—'}
        </div>
      </div>
      {throt?.any_event && (
        <div className="health-cell" style={{ background: 'rgba(255,82,82,0.15)' }}>
          <div className="health-label">⚠ THROTTLE</div>
          <div className="health-val" style={{ color: '#ff5252' }}>{throt.raw}</div>
        </div>
      )}
    </div>
  )
}

function formatUptime(s) {
  if (s < 60) return `${s.toFixed(0)}s`
  if (s < 3600) return `${(s / 60).toFixed(0)}m ${(s % 60).toFixed(0)}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}
