/**
 * Üstte sürekli görünen bir uyarı çubuğu — FSM ABORT durumunda kırmızı.
 */
export default function FailsafeBanner({ data }) {
  const aborted = data.fsm?.state === 'ABORT'
  if (!aborted) return null
  const reason = data.fsm?.abort_reason || 'Failsafe tetiklendi'
  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, zIndex: 9999,
      background: 'linear-gradient(90deg, #b00020, #ff5252, #b00020)',
      backgroundSize: '200% 100%',
      animation: 'failsafePulse 1.4s linear infinite',
      color: '#fff', fontFamily: 'Courier New', fontWeight: 'bold',
      padding: '8px 16px', textAlign: 'center', letterSpacing: 2,
      borderBottom: '2px solid #4a0010',
      boxShadow: '0 4px 18px rgba(255,80,80,0.5)',
    }}>
      ⚠ FAILSAFE / ABORT — {reason.toUpperCase()} ⚠
      <style>{`
        @keyframes failsafePulse {
          0%   { background-position: 0% 0; }
          100% { background-position: 200% 0; }
        }
      `}</style>
    </div>
  )
}
