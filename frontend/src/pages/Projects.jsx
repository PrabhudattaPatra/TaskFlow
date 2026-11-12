import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { Button, ErrorState, Field, Loading, Modal } from '../components/ui'
import { useSocketEvents } from '../context/SocketContext'
import { useAction, useAsync } from '../hooks'

function NewProject({ onClose }) {
  const nav = useNavigate()
  const [form, setForm] = useState({ name: '', description: '' })
  const [errors, setErrors] = useState({})
  const [submit, busy] = useAction(async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return setErrors({ name: 'Project name is required' })
    try {
      const p = await api('/projects', { method: 'POST', body: form })
      nav(`/projects/${p.id}`)
    } catch (err) {
      setErrors(Object.keys(err.fieldErrors || {}).length ? err.fieldErrors : { form: err.message })
    }
  })
  return (
    <Modal title="New project" onClose={onClose}>
      <form onSubmit={submit} noValidate>
        {errors.form && <div className="banner error">{errors.form}</div>}
        <Field label="Name" error={errors.name}><input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Description" error={errors.description}><textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <div className="actions"><Button className="primary" busy={busy} busyLabel="Creating…">Create project</Button></div>
      </form>
    </Modal>
  )
}

export default function Projects() {
  const { data, loading, error, reload } = useAsync(() => api('/projects'), [])
  const [creating, setCreating] = useState(false)
  useSocketEvents((e) => {
    if (['project.added', 'project.removed', 'project.deleted', 'resync'].includes(e.type)) reload(true)
  })

  return (
    <>
      <div className="page-head"><h2>Projects</h2><button className="btn primary" onClick={() => setCreating(true)}>+ New project</button></div>
      {loading && <Loading />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data && data.length === 0 && <div className="card muted">You are not in any project yet. Create one to get started.</div>}
      <div className="grid">
        {data?.map((p) => (
          <Link key={p.id} to={`/projects/${p.id}`} className="card project-card">
            <h3>{p.name}</h3>
            <p className="muted">{p.description || 'No description'}</p>
            <div className="meta"><span className={`badge role-${p.my_role}`}>{p.my_role}</span><small>{p.member_count} members · {p.open_task_count} open</small></div>
          </Link>
        ))}
      </div>
      {creating && <NewProject onClose={() => setCreating(false)} />}
    </>
  )
}
