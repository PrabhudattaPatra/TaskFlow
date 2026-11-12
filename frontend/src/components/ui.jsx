import { useSocket } from '../context/SocketContext'

export const Loading = ({ label = 'Loading…' }) => (
  <div className="state" role="status"><span className="spinner" /> {label}</div>
)

export const ErrorState = ({ error, onRetry }) => (
  <div className="state error" role="alert">
    <p>{error?.message || 'Something went wrong.'}</p>
    {onRetry && <button className="btn" onClick={() => onRetry()}>Try again</button>}
  </div>
)

export const Button = ({ busy, children, className = '', busyLabel, ...rest }) => (
  <button className={`btn ${className}`} disabled={busy || rest.disabled} {...rest}>
    {busy ? <><span className="spinner sm" /> {busyLabel || 'Working…'}</> : children}
  </button>
)

export const Field = ({ label, error, children }) => (
  <label className="field">
    <span>{label}</span>
    {children}
    {error && <small className="field-error" role="alert">{error}</small>}
  </label>
)

export const Avatar = ({ user, size = 24 }) => (
  <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.45 }} title={user?.name}>
    {(user?.name || '?').slice(0, 1).toUpperCase()}
  </span>
)

export const PriorityBadge = ({ priority }) => <span className={`badge p-${priority}`}>{priority}</span>

export function ConnectionBadge() {
  const { status } = useSocket()
  const label = { online: 'Live', connecting: 'Connecting…', offline: 'Reconnecting…' }[status]
  return <span className={`conn ${status}`} title="Real-time connection"><i /> {label}</span>
}

export function Modal({ title, onClose, children, wide }) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-label={title}>
        <header><h3>{title}</h3><button className="icon-btn" onClick={onClose} aria-label="Close">✕</button></header>
        {children}
      </div>
    </div>
  )
}
