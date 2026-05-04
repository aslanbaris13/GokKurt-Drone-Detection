import { useEffect, useRef, useState } from 'react'
import CameraPanel from './components/CameraPanel'
import MapPanel from './components/MapPanel'
import BottomBar from './components/BottomBar'
import EventLogPanel from './components/EventLogPanel'
import ParameterPanel from './components/ParameterPanel'
import PreFlightChecklist from './components/PreFlightChecklist'
import FailsafeBanner from './components/FailsafeBanner'
import SystemHealthStrip from './components/SystemHealthStrip'
import Sparkline from './components/Sparkline'
import { useGokKurtData } from './hooks/useGokKurtData'

const HISTORY_LEN = 80

export default function App() {
  const data = useGokKurtData()
  const [clock, setClock] = useState(new Date())
  const [showParams, setShowParams]      = useState(false)
  const [showChecklist, setShowChecklist] = useState(false)

  // Sparkline tarihçeleri
  const [confHist, setConfHist]       = useState([])
  const [bboxHist, setBboxHist]       = useState([])
  const [fpsHist, setFpsHist]         = useState([])
  const [cpuHist, setCpuHist]         = useState([])
  const [scoreHist, setScoreHist]     = useState([])
  const lastTickRef = useRef(0)

  useEffect(() => {
    const id = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  // ~5 Hz tarihçe
  useEffect(() => {
    const now = performance.now()
    if (now - lastTickRef.current < 200) return
    lastTickRef.current = now
    setConfHist((h)  => [...h.slice(-(HISTORY_LEN - 1)), data.confidence ?? 0])
    setBboxHist((h)  => [...h.slice(-(HISTORY_LEN - 1)), data.bboxPct ?? 0])
    setFpsHist((h)   => [...h.slice(-(HISTORY_LEN - 1)), data.fps ?? 0])
    setCpuHist((h)   => [...h.slice(-(HISTORY_LEN - 1)), data.telemetry?.cpu_pct ?? data.gpuUsage ?? 0])
    setScoreHist((h) => [...h.slice(-(HISTORY_LEN - 1)), data.targetScore ?? 0])
  }, [data])

  const timeStr = clock.toLocaleTimeString('tr-TR', { hour12: false })
  const dateStr = clock.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' })

  return (
    <div className="app">
      <FailsafeBanner data={data} />

      <header className="header">
        <div className="header-left">
          <span className="logo">✦ GÖKKURT</span>
          <span className="hdiv" />
          <span className="subtitle">YER KONTROL İSTASYONU</span>
          <span className="hdiv" />
          <span className="subtitle">SAVAŞAN İHA 2026</span>
        </div>
        <div className="header-center">
          <span className={`mission-badge ${data.online ? '' : 'offline'}`}>
            {data.online ? '● CANLI BAĞLANTI (Pi)' : '○ SİMÜLASYON MODU'}
          </span>
        </div>
        <div className="header-right">
          <span className="clock">{timeStr}</span>
          <span className="hdiv" />
          <span className="date-display">{dateStr}</span>
        </div>
      </header>

      <div className="main-panels">
        <CameraPanel data={data} />
        <MapPanel data={data} />
      </div>

      <div className="aux-row">
        <div className="aux-col aux-col-sparklines">
          <Sparkline label="CONFIDENCE" value={(data.confidence * 100).toFixed(1)} suffix="%"
                     values={confHist} color="#00b4ff" min={0} max={1} height={30} />
          <Sparkline label="BBOX %" value={(data.bboxPct ?? 0).toFixed(2)} suffix="%"
                     values={bboxHist} color="#ffb300" min={0} max={Math.max(10, ...bboxHist, 1)} height={30} />
          <Sparkline label="FPS" value={(data.fps ?? 0).toFixed(1)}
                     values={fpsHist} color="#00e676" min={0} max={Math.max(35, ...fpsHist, 1)} height={30} />
          <Sparkline label="CPU/GPU %" value={(data.telemetry?.cpu_pct ?? data.gpuUsage ?? 0).toFixed(0)} suffix="%"
                     values={cpuHist} color="#b388ff" min={0} max={100} height={30} />
          <Sparkline label="HEDEF SKORU" value={(data.targetScore ?? 0).toFixed(0)} suffix="/100"
                     values={scoreHist} color="#ff6d00" min={0} max={100} height={30} />
        </div>
        <EventLogPanel events={data.events} />
      </div>

      <SystemHealthStrip telemetry={data.telemetry} />

      <BottomBar
        data={data}
        onOpenParams={() => setShowParams(true)}
        onOpenChecklist={() => setShowChecklist(true)}
      />

      {showParams && <ParameterPanel onClose={() => setShowParams(false)} />}
      {showChecklist && (
        <PreFlightChecklist
          data={data}
          onClose={() => setShowChecklist(false)}
          onStart={() => {
            fetch(`http://${location.hostname}:8000/api/mission/start`, { method: 'POST' })
              .catch(() => {})
          }}
        />
      )}
    </div>
  )
}
