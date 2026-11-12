import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useAuth } from './AuthContext'
import { getAccessToken, refreshSession } from '../api/client'

const SocketContext = createContext(null)
export const useSocket = () => useContext(SocketContext)

/**
 * One authenticated WebSocket per logged-in user.
 * - Auth: access JWT sent as ?token= on the handshake (browsers cannot set WS headers).
 * - Rooms: components call watchProject(id); the server verifies membership before joining the room.
 * - Disconnects: exponential-backoff reconnect, re-subscribe to watched projects, then emit a
 *   'resync' event so views refetch whatever they missed while offline.
 */
export function SocketProvider({ children }) {
  const { user } = useAuth()
  const [status, setStatus] = useState('offline') // connecting | online | offline
  const ws = useRef(null)
  const listeners = useRef(new Set())
  const watched = useRef(new Map()) // project_id -> refcount
  const retry = useRef(0)
  const timer = useRef(null)
  const alive = useRef(false)
  const wasOpen = useRef(false)

  const emit = (evt) => listeners.current.forEach((fn) => fn(evt))
  const send = (obj) => { if (ws.current?.readyState === 1) ws.current.send(JSON.stringify(obj)) }

  const connect = useCallback(() => {
    if (!alive.current) return
    setStatus('connecting')
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const sock = new WebSocket(`${proto}://${location.host}/api/ws?token=${encodeURIComponent(getAccessToken() || '')}`)
    ws.current = sock
    let opened = false
    sock.onopen = () => {
      opened = true
      retry.current = 0
      setStatus('online')
      watched.current.forEach((_, pid) => send({ action: 'subscribe', project_id: pid }))
      if (wasOpen.current) emit({ type: 'resync' }) // events may have been missed while offline
      wasOpen.current = true
    }
    sock.onmessage = (m) => { try { emit(JSON.parse(m.data)) } catch { /* ignore */ } }
    sock.onclose = async (e) => {
      if (ws.current !== sock) return
      setStatus('offline')
      if (!alive.current) return
      // A rejected handshake surfaces in browsers as a plain failed connection (never opened), often an
      // expired access token: refresh it before retrying. If the refresh is refused, the session is over.
      if (!opened || e.code === 4401) {
        try { await refreshSession() } catch (err) { if (err.status === 401) return }
      }
      const delay = Math.min(1000 * 2 ** retry.current++, 15000)
      timer.current = setTimeout(connect, delay)
    }
  }, [])

  useEffect(() => {
    if (!user) return undefined
    alive.current = true
    wasOpen.current = false
    connect()
    const ping = setInterval(() => send({ action: 'ping' }), 30000)
    return () => {
      alive.current = false
      clearInterval(ping)
      clearTimeout(timer.current)
      const s = ws.current
      ws.current = null
      s?.close()
    }
  }, [user, connect])

  const subscribe = useCallback((fn) => {
    listeners.current.add(fn)
    return () => listeners.current.delete(fn)
  }, [])

  const watchProject = useCallback((id) => {
    watched.current.set(id, (watched.current.get(id) || 0) + 1)
    send({ action: 'subscribe', project_id: id })
    return () => {
      const n = (watched.current.get(id) || 1) - 1
      if (n <= 0) { watched.current.delete(id); send({ action: 'unsubscribe', project_id: id }) }
      else watched.current.set(id, n)
    }
  }, [])

  return <SocketContext.Provider value={{ status, subscribe, watchProject }}>{children}</SocketContext.Provider>
}

/** Run `handler` for each socket event while the component is mounted. */
export function useSocketEvents(handler) {
  const { subscribe } = useSocket()
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => subscribe((e) => ref.current(e)), [subscribe])
}
