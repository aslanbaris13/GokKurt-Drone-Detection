import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, Polygon, Circle, Polyline, useMap, LayersControl } from 'react-leaflet'
import L from 'leaflet'
import { WAYPOINTS, FLIGHT_BOUNDARY, HSS_ZONES } from '../constants'

// Leaflet default icon fix
delete L.Icon.Default.prototype._getIconUrl

const PLANNED_ROUTE = [...WAYPOINTS, WAYPOINTS[0]]

const ENEMY_START = [40.8515, 31.1638]

function createOwnIcon(heading) {
  const rot = (heading || 0).toFixed(0)
  return L.divIcon({
    className: '',
    html: `<div style="
      width:0; height:0;
      border-left:8px solid transparent;
      border-right:8px solid transparent;
      border-bottom:20px solid #00e676;
      transform:rotate(${rot}deg);
      filter: drop-shadow(0 0 6px #00e676);
    "></div>`,
    iconAnchor: [8, 10],
  })
}

const enemyIcon = L.divIcon({
  className: '',
  html: `<div style="
    width:14px; height:14px;
    background:#f44336;
    border-radius:50%;
    border:2px solid #ff8a80;
    box-shadow:0 0 8px #f44336, 0 0 16px rgba(244,67,54,0.4);
    animation:pulse-red 1.2s infinite;
  "></div>`,
  iconAnchor: [7, 7],
})

// Leaflet harita boyutunu otomatik düzelt
function MapResizer() {
  const map = useMap()
  useEffect(() => {
    const timer = setTimeout(() => map.invalidateSize(), 200)
    return () => clearTimeout(timer)
  }, [map])
  return null
}

// Component that imperatively updates markers
function LiveMarkers({ data }) {
  const map = useMap()
  const ownRef = useRef(null)
  const enemyRef = useRef(null)
  const iconCacheRef = useRef(null)

  useEffect(() => {
    // Own UAV marker
    const icon = createOwnIcon(data.heading)
    if (!ownRef.current) {
      ownRef.current = L.marker([data.lat, data.lon], { icon, zIndexOffset: 100 })
        .addTo(map)
        .bindTooltip('Bizim İHA', { permanent: false, direction: 'top', className: 'map-tooltip' })
    } else {
      ownRef.current.setLatLng([data.lat, data.lon])
      if (Math.abs(data.heading - (iconCacheRef.current || 0)) > 2) {
        ownRef.current.setIcon(createOwnIcon(data.heading))
        iconCacheRef.current = data.heading
      }
    }

    // Enemy UAV marker
    if (!enemyRef.current) {
      enemyRef.current = L.marker([data.enemyLat, data.enemyLon], { icon: enemyIcon, zIndexOffset: 90 })
        .addTo(map)
        .bindTooltip('Düşman İHA', { permanent: false, direction: 'top', className: 'map-tooltip-enemy' })
    } else {
      enemyRef.current.setLatLng([data.enemyLat, data.enemyLon])
    }

    return () => {}
  }, [data.lat, data.lon, data.enemyLat, data.enemyLon, data.heading, map])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (ownRef.current) { ownRef.current.remove(); ownRef.current = null }
      if (enemyRef.current) { enemyRef.current.remove(); enemyRef.current = null }
    }
  }, [])

  return null
}

export default function MapPanel({ data }) {
  return (
    <div className="panel map-panel">
      <div className="panel-header">
        <span className="panel-title">HARİTA GÖRÜNÜMİ &amp; ROTA</span>
        <div className="panel-badges">
          <span className="badge green">● GPS 3D Fix</span>
          <span className="badge blue">12 UYDU</span>
        </div>
      </div>

      <div className="map-wrapper">
        <MapContainer
          center={[40.9048, 31.1830]}
          zoom={15}
          style={{ width: '100%', height: '100%' }}
          zoomControl={false}
          attributionControl={false}
        >
          <MapResizer />
          {/* Birden fazla tile seçeneği — biri yüklenemezse diğeri devreye girer */}
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution=""
            opacity={0.25}
          />
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution=""
            opacity={1}
          />

          {/* Flight boundary */}
          <Polygon
            positions={FLIGHT_BOUNDARY}
            pathOptions={{
              color: '#ffcc00',
              weight: 1.5,
              dashArray: '8,6',
              fillOpacity: 0.04,
              fillColor: '#ffcc00',
            }}
          />

          {/* HSS zones */}
          {HSS_ZONES.map((z, i) => (
            <Circle
              key={i}
              center={z.center}
              radius={z.radius}
              pathOptions={{
                color: '#f44336',
                weight: 2,
                fillColor: '#f44336',
                fillOpacity: 0.18,
                dashArray: '5,4',
              }}
            />
          ))}

          {/* Planned route */}
          <Polyline
            positions={PLANNED_ROUTE}
            pathOptions={{ color: '#00b4ff', weight: 1.5, opacity: 0.7, dashArray: '10,5' }}
          />

          {/* Completed route so far */}
          <Polyline
            positions={[WAYPOINTS[0], [data.lat, data.lon]]}
            pathOptions={{ color: '#00e676', weight: 2, opacity: 0.9 }}
          />

          <LiveMarkers data={data} />
        </MapContainer>

        {/* Map legend overlay */}
        <div className="map-legend">
          <div className="legend-item"><span className="leg-dot" style={{ background: '#00e676' }} />Bizim İHA</div>
          <div className="legend-item"><span className="leg-dot" style={{ background: '#f44336' }} />Düşman İHA</div>
          <div className="legend-item"><span className="leg-line" style={{ borderColor: '#ffcc00', borderStyle: 'dashed' }} />Uçuş Sınırı</div>
          <div className="legend-item"><span className="leg-line" style={{ borderColor: '#f44336' }} />HSS Bölgesi</div>
          <div className="legend-item"><span className="leg-line" style={{ borderColor: '#00b4ff', borderStyle: 'dashed' }} />Planlanan Rota</div>
        </div>

        {/* Coordinate overlay */}
        <div className="map-coords">
          <span>{data.lat.toFixed(5)}° N</span>
          <span>{data.lon.toFixed(5)}° E</span>
        </div>
      </div>
    </div>
  )
}
