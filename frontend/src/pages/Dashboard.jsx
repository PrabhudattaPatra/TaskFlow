import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorState, Loading } from '../components/ui'
import { useSocketEvents } from '../context/SocketContext'
import { fmtTime, STATUSES, useAsync } from '../hooks'

export default function Dashboard() {
  const { data, loading, error, reload } = useAsync(() => api('/me/dashboard'), [])
  useSocketEvents((e) => {
    if (['assigned.changed', 'project.added', 'project.removed', 'project.deleted', 'resync'].includes(e.type)) reload(true)
  })

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />

  return (
    <>
      <h2>Dashboard</h2>
      <div className="stats">
        <div className="card stat"><b>{data.project_count}</b><span>Projects</span></div>
        {STATUSES.map(([k, label]) => (
          <div className="card stat" key={k}><b>{data.assigned_by_status[k]}</b><span>Assigned · {label}</span></div>
        ))}
        <div className="card stat"><b>{data.completed_this_week}</b><span>Completed this week</span></div>
        <div className="card stat wide">
          {data.busiest_project
            ? <><b><Link to={`/projects/${data.busiest_project.id}`}>{data.busiest_project.name}</Link></b><span>Most open tasks ({data.busiest_project.open_tasks})</span></>
            : <><b>—</b><span>No open tasks</span></>}
        </div>
      </div>
      <h3>Your recent activity</h3>
      <div className="card">
        {data.recent_activity.length === 0 && <p className="muted">Nothing yet.</p>}
        <ul className="feed">
          {data.recent_activity.map((a) => (
            <li key={a.id}>
              <span>{a.message}</span>
              <small>{a.project_name && <Link to={`/projects/${a.project_id}`}>{a.project_name}</Link>} · {fmtTime(a.created_at)}</small>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
