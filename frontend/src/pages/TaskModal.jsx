import { useState } from 'react'
import { api } from '../api/client'
import { Avatar, Button, ErrorState, Field, Loading, Modal } from '../components/ui'
import { useSocketEvents } from '../context/SocketContext'
import { fmtTime, STATUSES, useAction, useAsync } from '../hooks'

const todayStr = () => new Date().toISOString().slice(0, 10)

function Comments({ projectId, taskId }) {
  const base = `/projects/${projectId}/tasks/${taskId}/comments`
  const { data, loading, error, reload, setData } = useAsync(() => api(base), [taskId])
  const [body, setBody] = useState('')
  const [err, setErr] = useState('')

  useSocketEvents((e) => {
    if (e.type === 'comment.added' && e.task_id === taskId) {
      setData((list) => (list && !list.some((c) => c.id === e.comment.id) ? [...list, e.comment] : list))
    }
    if (e.type === 'resync') reload(true)
  })

  const [send, busy] = useAction(async (ev) => {
    ev.preventDefault()
    if (!body.trim()) return setErr('Comment cannot be empty')
    setErr('')
    try {
      const c = await api(base, { method: 'POST', body: { body } })
      setData((list) => (list && !list.some((x) => x.id === c.id) ? [...list, c] : list))
      setBody('')
    } catch (e) { setErr(e.fieldErrors?.body || e.message) }
  })

  return (
    <section className="comments">
      <h4>Comments</h4>
      {loading && <Loading label="Loading comments…" />}
      {error && <ErrorState error={error} onRetry={reload} />}
      {data?.length === 0 && <p className="muted">No comments yet.</p>}
      {data?.map((c) => (
        <div className="comment" key={c.id}>
          <Avatar user={c.author} />
          <div><b>{c.author?.name || 'Deleted user'}</b> <small className="muted">{fmtTime(c.created_at)}</small><p>{c.body}</p></div>
        </div>
      ))}
      <form onSubmit={send} noValidate>
        <Field label="Add a comment" error={err}><textarea rows={2} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
        <Button className="primary" busy={busy} busyLabel="Posting…">Comment</Button>
      </form>
    </section>
  )
}

export default function TaskModal({ project, task, onClose, onSaved }) {
  const isNew = !task
  const [form, setForm] = useState({
    title: task?.title || '', description: task?.description || '', status: task?.status || 'todo',
    priority: task?.priority || 'medium', due_date: task?.due_date || '', assignee_id: task?.assignee?.id ?? '',
  })
  const [errors, setErrors] = useState({})
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const base = `/projects/${project.id}/tasks`

  const [save, busy] = useAction(async (e) => {
    e.preventDefault()
    const local = {}
    if (!form.title.trim()) local.title = 'Title cannot be empty'
    if (isNew && form.due_date && form.due_date < todayStr()) local.due_date = 'Due date cannot be in the past'
    if (Object.keys(local).length) return setErrors(local)
    setErrors({})
    const body = {
      title: form.title, description: form.description, status: form.status, priority: form.priority,
      due_date: form.due_date || null, assignee_id: form.assignee_id === '' ? null : Number(form.assignee_id),
    }
    try {
      await api(isNew ? base : `${base}/${task.id}`, { method: isNew ? 'POST' : 'PATCH', body })
      onSaved()
      onClose()
    } catch (err) {
      const fe = { ...err.fieldErrors }
      if (!Object.keys(fe).length) {
        // Non-field errors from business rules: attach to the most relevant field.
        if (/assignee/i.test(err.message)) fe.assignee_id = err.message
        else if (/done/i.test(err.message)) fe.status = err.message
        else fe.form = err.message
      }
      setErrors(fe)
    }
  })

  const [remove, removing] = useAction(async () => {
    try { await api(`${base}/${task.id}`, { method: 'DELETE' }); onSaved(); onClose() }
    catch (err) { setErrors({ form: err.message }) }
  })

  return (
    <Modal title={isNew ? 'New task' : 'Task'} onClose={onClose} wide>
      <form onSubmit={save} noValidate>
        {errors.form && <div className="banner error" role="alert">{errors.form}</div>}
        <Field label="Title" error={errors.title}><input autoFocus value={form.title} onChange={set('title')} /></Field>
        <Field label="Description" error={errors.description}><textarea rows={3} value={form.description} onChange={set('description')} /></Field>
        <div className="cols">
          <Field label="Status" error={errors.status}>
            <select value={form.status} onChange={set('status')}>{STATUSES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          </Field>
          <Field label="Priority" error={errors.priority}>
            <select value={form.priority} onChange={set('priority')}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>
          </Field>
          <Field label="Due date" error={errors.due_date}>
            <input type="date" value={form.due_date} min={isNew ? todayStr() : undefined} onChange={set('due_date')} />
          </Field>
          <Field label="Assignee" error={errors.assignee_id}>
            <select value={form.assignee_id} onChange={set('assignee_id')}>
              <option value="">Unassigned</option>
              {project.members.map((m) => <option key={m.user.id} value={m.user.id}>{m.user.name}</option>)}
            </select>
          </Field>
        </div>
        <div className="actions">
          {!isNew && <Button type="button" className="danger" busy={removing} busyLabel="Deleting…" onClick={remove}>Delete</Button>}
          <div className="spacer" />
          <Button className="primary" busy={busy} busyLabel="Saving…">{isNew ? 'Create task' : 'Save changes'}</Button>
        </div>
      </form>
      {!isNew && <Comments projectId={project.id} taskId={task.id} />}
    </Modal>
  )
}
