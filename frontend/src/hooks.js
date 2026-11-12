import { useCallback, useEffect, useRef, useState } from 'react'

/** Loads data with loading/error state; `reload(true)` refetches silently (no spinner flash). */
export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, loading: true, error: null })
  const fnRef = useRef(fn)
  fnRef.current = fn
  const seq = useRef(0)

  const reload = useCallback((silent = false) => {
    const id = ++seq.current
    if (!silent) setState((s) => ({ ...s, loading: true, error: null }))
    return fnRef.current()
      .then((data) => { if (id === seq.current) setState({ data, loading: false, error: null }) })
      .catch((error) => {
        if (id === seq.current) setState((s) => ({ data: silent ? s.data : null, loading: false, error: silent ? s.error : error }))
      })
  }, [])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { reload() }, deps)
  const setData = useCallback(
    (updater) => setState((s) => ({ ...s, data: typeof updater === 'function' ? updater(s.data) : updater })),
    [],
  )
  return { ...state, reload, setData }
}

/** Wraps an async action with a `busy` flag so buttons can disable and prevent double submits. */
export function useAction(fn) {
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const run = async (...args) => {
    if (busyRef.current) return undefined
    busyRef.current = true
    setBusy(true)
    try { return await fn(...args) } finally { busyRef.current = false; setBusy(false) }
  }
  return [run, busy]
}

export const fmtDate = (d) => (d ? new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—')
export const fmtTime = (d) => new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
export const STATUSES = [['todo', 'To Do'], ['in_progress', 'In Progress'], ['done', 'Done']]
export const STATUS_LABEL = Object.fromEntries(STATUSES)
