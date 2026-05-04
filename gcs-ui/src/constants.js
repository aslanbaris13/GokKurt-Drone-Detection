export const FSM_STATES = ['IDLE', 'İNTİKAL', 'DALIŞ', 'KİLİT', 'PAS_GEÇ', 'DÖNÜŞ']

// Pi sunucu adresi — demo sırasında Pi'nin IP'sine göre değiştir
export const PI_HOST = 'gokkurt.local'  // Pi hostname — veya IP: '192.168.x.x'
export const STREAM_URL = `http://${PI_HOST}:8000/stream`
export const WS_URL     = `ws://${PI_HOST}:8000/ws`

// Düzce Üniversitesi Konuralp Kampüsü — OSM doğrulanmış koordinatlar
export const WAYPOINTS = [
  [40.9018, 31.1795],
  [40.9038, 31.1835],
  [40.9062, 31.1868],
  [40.9080, 31.1848],
  [40.9070, 31.1800],
  [40.9042, 31.1772],
]

export const FLIGHT_BOUNDARY = [
  [40.8975, 31.1735],
  [40.8975, 31.1910],
  [40.9115, 31.1910],
  [40.9115, 31.1735],
]

export const HSS_ZONES = [
  { center: [40.9072, 31.1858], radius: 150, label: 'HSS-1' },
  { center: [40.9008, 31.1810], radius: 120, label: 'HSS-2' },
]
