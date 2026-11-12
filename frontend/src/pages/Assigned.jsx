import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorState, Loading, PriorityBadge } from '../components/ui'
import { useSocketEvents } from '../context/SocketContext'
import { fmtDate, STATUS_LABEL, useAsync } from '../hooks'

export default function Assigned() {
  const { data, loading, error, reload } = useAsync(() => api('/me/assigned'), [])
  // Live: server pings my user-room whenever a task is (un)assigned to/from me.
  useSocketEvents((e) => {
    if (['assigned.changed', 'task.updated', 'task.moved', 'task.deleted', 'project.removed', 'project.deleted', 'resync'].includes(e.type)) reload(true)
  })

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  return (
    <>
      <h2>Assigned to me</h2>
      {data.length === 0 && <div className="card muted">No tasks are assigned to you.</div>}
      <div className="list">
        {data.map((t) => (
          <Link key={t.id} to={`/projects/${t.project_id}?task=${t.id}`} className="card row-link">
            <div><b>{t.title}</b><br /><small className="muted">{t.project_name}</small></div>
            <div className="meta">
              <PriorityBadge priority={t.priority} />
              <span className={`status s-${t.status}`}>{STATUS_LABEL[t.status]}</span>
              <small>Due {fmtDate(t.due_date)}</small>
            </div>
          </Link>
        ))}
      </div>
    </>
  )
}
