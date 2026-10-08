import { useEffect } from 'react'
import { create } from 'zustand'

import { API_BASE_URL, refreshSession } from '@/lib/api-client'
import { useAuthStore } from '@/stores/auth-store'

/**
 * Realtime gateway client. Phase 1 maintains an authenticated connection with
 * a heartbeat; domain events (presence, activity, alerts, WebRTC signalling)
 * will be dispatched through `subscribe` in later phases.
 */
export type RealtimeStatus = 'idle' | 'connecting' | 'connected' | 'disconnected'

export interface RealtimeEvent {
  type: string
  payload: Record<string, unknown>
  ts: string
}

type Listener = (event: RealtimeEvent) => void

interface RealtimeState {
  status: RealtimeStatus
  setStatus: (status: RealtimeStatus) => void
}

export const useRealtimeStore = create<RealtimeState>()((set) => ({
  status: 'idle',
  setStatus: (status) => set({ status }),
}))

const listeners = new Set<Listener>()

export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function gatewayUrl(): string {
  const base = new URL(API_BASE_URL, window.location.origin)
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  base.pathname = `${base.pathname.replace(/\/$/, '')}/ws`
  return base.toString()
}

/**
 * The access token travels as a WebSocket subprotocol, never in the URL (URLs end up in proxy logs).
 * The server accepts `workpulse.v1`; see backend/app/websocket/auth.py.
 */
export function socketProtocols(token: string): string[] {
  return ['workpulse.v1', `bearer.${token}`]
}

const HEARTBEAT_MS = 25_000
const MAX_BACKOFF_MS = 30_000
const POLICY_VIOLATION = 1008
/** The server closes with this when the sign-in session was revoked or the account suspended. */
const SESSION_ENDED = 4401

/** Keeps one gateway connection open while the user is signed in. */
export function useRealtimeConnection() {
  const authenticated = useAuthStore((s) => s.status === 'authenticated')

  useEffect(() => {
    if (!authenticated) return
    const { setStatus } = useRealtimeStore.getState()
    let socket: WebSocket | null = null
    let heartbeat: number | undefined
    let reconnectTimer: number | undefined
    let attempts = 0
    let disposed = false

    const scheduleReconnect = () => {
      if (disposed) return
      const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempts)
      attempts += 1
      reconnectTimer = window.setTimeout(connect, delay)
    }

    function connect() {
      const token = useAuthStore.getState().accessToken
      if (disposed || !token) return
      setStatus('connecting')
      socket = new WebSocket(gatewayUrl(), socketProtocols(token))

      socket.onmessage = (message) => {
        let event: RealtimeEvent
        try {
          event = JSON.parse(String(message.data)) as RealtimeEvent
        } catch {
          return
        }
        if (event.type === 'connection.ready') {
          attempts = 0
          setStatus('connected')
          heartbeat = window.setInterval(() => socket?.send(JSON.stringify({ type: 'ping' })), HEARTBEAT_MS)
        }
        listeners.forEach((listener) => listener(event))
      }

      socket.onclose = (closeEvent) => {
        window.clearInterval(heartbeat)
        if (disposed) return
        setStatus('disconnected')
        if (closeEvent.code === POLICY_VIOLATION || closeEvent.code === SESSION_ENDED) {
          // Token expired (refresh and reconnect) or the session was signed out elsewhere (refresh fails: sign out here too).
          void refreshSession().then((session) => {
            if (session) scheduleReconnect()
            else if (closeEvent.code === SESSION_ENDED) useAuthStore.getState().clearSession()
          })
          return
        }
        scheduleReconnect()
      }
    }

    connect()
    return () => {
      disposed = true
      window.clearInterval(heartbeat)
      window.clearTimeout(reconnectTimer)
      socket?.close(1000)
      setStatus('idle')
    }
  }, [authenticated])
}
