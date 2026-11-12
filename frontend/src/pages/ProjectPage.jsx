import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, qs } from '../api/client'
import { Avatar, Button, ErrorState, Field, Loading, PriorityBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useSocket, useSocketEvents } from '../context/SocketContext'
import { fmtDate, fmtTime, STATUSES, STATUS_LABEL, useAction, useAsync } from '../hooks'
import TaskModal from './TaskModal'

function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}

function Filters({ project, f, setF }) {
  return (
    <div className="filters">
      <input placeholder="Search title…" value={f.search} onChange={(e) => setF({ ...f, search: e.target.value, page: 1 })} />
      <select value={f.assignee} onChange={(e) => setF({ ...f, assignee: e.target.value, page: 1 })}>
        <option value="">All assignees</option><option value="unassigned">Unassigned</option>
        {project.members.map((m) => <option key={m.user.id} value={m.user.id}>{m.user.name}</option>)}
      </select>
      <select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value, page: 1 })}>
        <option value="">All priorities</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
      </select>
    </div>
  )
}

function TaskCard({ t, onOpen, draggable, onDragStart }) {
  const overdue = t.due_date && t.status !== 'done' && new Date(t.due_date) < new Date(new Date().toDateString())
  return (
    <div className="task" draggable={draggable} onDragStart={onDragStart} onClick={() => onOpen(t)}>
      <div className="task-title">{t.title}</div>
      <div className="meta">
        <PriorityBadge priority={t.priority} />
        {t.due_date && <small className={overdue ? 'overdue' : 'muted'}>Due {fmtDate(t.due_date)}</small>}
        <div className="spacer" />
        {t.assignee && <Avatar user={t.assignee} />}
      </div>
    </div>
  )
}

function Board({ project, filters, tick, onOpen, flash }) {
  const { data, loading, error, reload, setData } = useAsync(
    () => api(`/projects/${project.id}/board${qs(filters)}`), [project.id, filters.assignee, filters.priority, filters.search])
  useEffect(() => { if (tick) reload(true) }, [tick]) // eslint-disable-line react-hooks/exhaustive-deps
  const [over, setOver] = useState(null)

  const drop = async (status, e) => {
    e.preventDefault(); setOver(null)
    const id = Number(e.dataTransfer.getData('text/plain'))
    const t = data?.find((x) => x.id === id)
    if (!t || t.status === status) return
    const snapshot = data
    setData((list) => list.map((x) => (x.id === id ? { ...x, status } : x))) // optimistic
    try { await api(`/projects/${project.id}/tasks/${id}/move`, { method: 'POST', body: { status } }); reload(true) }
    catch (err) { setData(snapshot); flash(err.message) } // rollback + clear message
  }

  if (loading) return <Loading />
  if (error) return <ErrorState error={error} onRetry={reload} />
  return (
    <div className="board">
      {STATUSES.map(([key, label]) => {
        const items = data.filter((t) => t.status === key)
        return (
          <div key={key} className={`column ${over === key ? 'over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setOver(key) }} onDragLeave={() => setOver(null)} onDrop={(e) => drop(key, e)}>
            <h4>{label} <span className="count">{items.length}</span></h4>
            {items.map((t) => <TaskCard key={t.id} t={t} onOpen={onOpen} draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', String(t.id))} />)}
            {items.length === 0 && <p className="muted empty">No tasks</p>}
          </div>
        )
      })}
    </div>
  )
}

function Backlog({ project, filters, setFilters, tick, onOpen }) {
  const params = { page: filters.page, page_size: 8, assignee: filters.assignee, priority: filters.priority, search: filters.search, sort_by: filters.sort_by, order: filters.order }
  const { data, loading, error, reload } = useAsync(
    () => api(`/projects/${project.id}/tasks${qs(params)}`),
    [project.id, filters.page, filters.assignee, filters.priority, filters.search, filters.sort_by, filters.order])
  useEffect(() => { if (tick) reload(true) }, [tick]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="filters">
        <label>Sort by&nbsp;
          <select value={filters.sort_by} onChange={(e) => setFilters({ ...filters, sort_by: e.target.value, page: 1 })}>
            <option value="created_at">Date created</option><option value="priority">Priority</option><option value="due_date">Due date</option>
          </select>
        </label>
        <select value={filters.order} onChange={(e) => setFilters({ ...filters, order: e.target.value, page: 1 })}>
          <option value="desc">Descending</option><option value="asc">Ascending</option>
        </select>
      </div>
      {loading && <Loading />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <>
          <div className="card table-wrap">
            <table>
              <thead><tr><th>Title</th><th>Status</th><th>Priority</th><th>Due</th><th>Assignee</th><th>Created</th></tr></thead>
              <tbody>
                {data.items.map((t) => (
                  <tr key={t.id} onClick={() => onOpen(t)}>
                    <td>{t.title}</td><td><span className={`status s-${t.status}`}>{STATUS_LABEL[t.status]}</span></td>
                    <td><PriorityBadge priority={t.priority} /></td><td>{fmtDate(t.due_date)}</td>
                    <td>{t.assignee?.name || '—'}</td><td>{fmtDate(t.created_at)}</td>
                  </tr>
                ))}
                {data.items.length === 0 && <tr><td colSpan={6} className="muted">No tasks match.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <button className="btn" disabled={filters.page <= 1} onClick={() => setFilters({ ...filters, page: filters.page - 1 })}>← Prev</button>
            <span>Page {data.page} of {data.pages} · {data.total} tasks</span>
            <button className="btn" disabled={filters.page >= data.pages} onClick={() => setFilters({ ...filters, page: filters.page + 1 })}>Next →</button>
          </div>
        </>
      )}
    </>
  )
}

function Members({ project, isOwner, onChanged, flash }) {
  const { user } = useAuth()
  const [email, setEmail] = useState('')
  const [err, setErr] = useState('')
  const [invite, inviting] = useAction(async (e) => {
    e.preventDefault()
    if (!/^\S+@\S+\.\S+$/.test(email)) return setErr('Enter a valid email address')
    setErr('')
    try { await api(`/projects/${project.id}/members`, { method: 'POST', body: { email } }); setEmail(''); onChanged() }
    catch (e2) { setErr(e2.fieldErrors?.email || e2.message) }
  })
  const [remove, removing] = useAction(async (uid) => {
    try { await api(`/projects/${project.id}/members/${uid}`, { method: 'DELETE' }); onChanged() }
    catch (e2) { flash(e2.message) }
  })
  return (
    <div className="card">
      <h4>Members</h4>
      <ul className="members">
        {project.members.map((m) => (
          <li key={m.user.id}>
            <Avatar user={m.user} /> <span>{m.user.name} <small className="muted">{m.user.email}</small></span>
            <span className={`badge role-${m.role}`}>{m.role}</span>
            {isOwner && m.user.id !== user.id && <button className="btn sm danger" disabled={removing} onClick={() => remove(m.user.id)}>Remove</button>}
          </li>
        ))}
      </ul>
      {isOwner && (
        <form onSubmit={invite} noValidate className="invite">
          <Field label="Invite by email" error={err}><input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@example.com" /></Field>
          <Button className="primary" busy={inviting} busyLabel="Inviting…">Invite</Button>
        </form>
      )}
    </div>
  )
}

function ActivityFeed({ items }) {
  return (
    <aside className="card activity">
      <h4>Activity</h4>
      {items.length === 0 && <p className="muted">No activity yet.</p>}
      <ul className="feed">
        {items.map((a) => <li key={a.id}><span>{a.message}</span><small>{fmtTime(a.created_at)}</small></li>)}
      </ul>
    </aside>
  )
}

export default function ProjectPage() {
  const { id } = useParams()
  const projectId = Number(id)
  const nav = useNavigate()
  const { watchProject } = useSocket()
  const [search, setSearch] = useSearchParams()
  const [tab, setTab] = useState('board')
  const [filters, setFilters] = useState({ search: '', assignee: '', priority: '', sort_by: 'created_at', order: 'desc', page: 1 })
  const debounced = useDebounced(filters.search)
  const effective = { ...filters, search: debounced }
  const [tick, setTick] = useState(0)
  const [editing, setEditing] = useState(null) // null | 'new' | task
  const [toast, setToast] = useState('')

  const project = useAsync(() => api(`/projects/${projectId}`), [projectId])
  const activity = useAsync(() => api(`/projects/${projectId}/activity`), [projectId])
  const flash = (m) => { setToast(m); setTimeout(() => setToast(''), 4000) }

  useEffect(() => watchProject(projectId), [projectId, watchProject]) // join this project's socket room

  const refreshAll = () => { setTick((t) => t + 1); activity.reload(true) }

  useSocketEvents((e) => {
    if (e.type === 'resync') { project.reload(true); refreshAll(); return }
    if (e.project_id !== projectId) return
    if (e.activity) activity.setData((list) => (list && !list.some((a) => a.id === e.activity.id) ? [e.activity, ...list] : list))
    if (e.type.startsWith('task.') || e.type === 'comment.added') setTick((t) => t + 1)
    if (e.type === 'member.invited' || e.type === 'member.removed') { project.reload(true); setTick((t) => t + 1) }
  })

  // Deep link from "Assigned to me": ?task=ID opens that task.
  const deepTask = search.get('task')
  useEffect(() => {
    if (!deepTask || !project.data) return
    api(`/projects/${projectId}/tasks/${deepTask}`).then(setEditing).catch(() => {}).finally(() => setSearch({}, { replace: true }))
  }, [deepTask, project.data, projectId, setSearch])

  const [confirmDel, setConfirmDel] = useState(false)
  const [del, deleting] = useAction(async () => {
    if (!confirmDel) { setConfirmDel(true); setTimeout(() => setConfirmDel(false), 4000); return }
    try { await api(`/projects/${projectId}`, { method: 'DELETE' }); nav('/projects') } catch (e) { flash(e.message) }
  })

  if (project.loading) return <Loading />
  if (project.error) return <ErrorState error={project.error} onRetry={project.reload} />
  const p = project.data
  const isOwner = p.my_role === 'owner'

  return (
    <>
      <div className="page-head">
        <div><h2>{p.name}</h2><p className="muted">{p.description}</p></div>
        <div className="head-actions">
          <button className="btn primary" onClick={() => setEditing('new')}>+ New task</button>
          {isOwner && <Button className="danger" busy={deleting} busyLabel="Deleting…" onClick={del}>{confirmDel ? 'Click again to confirm' : 'Delete project'}</Button>}
        </div>
      </div>
      {toast && <div className="banner error" role="alert">{toast}</div>}
      <div className="tabs">
        {[['board', 'Board'], ['backlog', 'Backlog'], ['members', `Members (${p.members.length})`]].map(([k, l]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      <div className="layout">
        <div className="main-col">
          {tab !== 'members' && <Filters project={p} f={filters} setF={setFilters} />}
          {tab === 'board' && <Board project={p} filters={{ assignee: effective.assignee, priority: effective.priority, search: effective.search }} tick={tick} onOpen={setEditing} flash={flash} />}
          {tab === 'backlog' && <Backlog project={p} filters={effective} setFilters={setFilters} tick={tick} onOpen={setEditing} />}
          {tab === 'members' && <Members project={p} isOwner={isOwner} onChanged={() => { project.reload(true); refreshAll() }} flash={flash} />}
        </div>
        {activity.error ? <ErrorState error={activity.error} onRetry={activity.reload} /> : activity.loading ? <Loading /> : <ActivityFeed items={activity.data} />}
      </div>
      {editing && (
        <TaskModal key={editing === 'new' ? 'new' : editing.id} project={p} task={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)} onSaved={refreshAll} />
      )}
    </>
  )
}
