import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'

import { api, API_BASE_URL, refreshSession } from '@/lib/api-client'
import { socketProtocols } from '@/lib/realtime'
import { useAuthStore } from '@/stores/auth-store'

/**
 * Viewer side of a live session: signalling over the session WebSocket, media over WebRTC.
 *
 * The browser always offers (receive-only video) and the agent answers with its screen track.
 * Recovery, in increasing order of severity:
 * - media path lost (ICE `disconnected` for a few seconds, or `failed`): renegotiate with a fresh
 *   offer on a new peer connection;
 * - signalling socket dropped: reconnect with back-off and a fresh token; the server keeps the
 *   session for a grace period, then we renegotiate;
 * - agent dropped (`peer_left`): wait for `peer_ready`, then renegotiate;
 * - this browser's network went away (`offline`): stop spending reconnect attempts until it's back, then
 *   reconnect at once; a network change (`online`, or `navigator.connection` changing, e.g. Wi-Fi to
 *   Ethernet) renegotiates immediately instead of waiting for ICE to notice.
 *
 * A browser refresh closes the socket without a stop; the server keeps the session for its grace period
 * and the reloaded page reconnects to the same session id.
 */
export type StreamPhase = 'connecting' | 'waiting' | 'negotiating' | 'live' | 'reconnecting' | 'ended'
export type StreamQuality = 'good' | 'fair' | 'poor'

export interface StreamStats {
  rttMs: number | null
  lossPct: number | null
  fps: number | null
  kbps: number | null
  width: number | null
  height: number | null
  quality: StreamQuality | null
}

const EMPTY_STATS: StreamStats = {
  rttMs: null,
  lossPct: null,
  fps: null,
  kbps: null,
  width: null,
  height: null,
  quality: null,
}
const DISCONNECTED_GRACE_MS = 4000
const MAX_SOCKET_ATTEMPTS = 6
const STOP_DELAY_MS = 400

/** Leaving the viewer ends the stream; a remount within moments (e.g. React StrictMode) cancels that. */
const pendingStops = new Map<string, number>()

/** Network Information API (Chromium); absent elsewhere, where `online` events still apply. */
type NetworkConnection = EventTarget | undefined
function networkConnection(): NetworkConnection {
  return (navigator as Navigator & { connection?: EventTarget }).connection
}

function socketUrl(sessionId: string): string {
  const base = new URL(API_BASE_URL, window.location.origin)
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  // WebRTC signalling only (offer/answer/ICE); video never passes through the API. See docs/live-tracking.md.
  base.pathname = `${base.pathname.replace(/\/$/, '')}/live/signaling/${sessionId}`
  return base.toString()
}

export function qualityOf(stats: Pick<StreamStats, 'rttMs' | 'lossPct' | 'fps'>): StreamQuality | null {
  if (stats.fps === null) return null
  const rtt = stats.rttMs ?? 0
  const loss = stats.lossPct ?? 0
  if (rtt < 150 && loss < 2 && stats.fps >= 6) return 'good'
  if (rtt < 400 && loss < 8 && stats.fps >= 3) return 'fair'
  return 'poor'
}

export function useLiveStream(sessionId: string | undefined, videoRef: RefObject<HTMLVideoElement | null>) {
  const [phase, setPhase] = useState<StreamPhase>('connecting')
  const [endReason, setEndReason] = useState<string | null>(null)
  const [agentOnline, setAgentOnline] = useState<boolean | null>(null)
  const [connectedAt, setConnectedAt] = useState<number | null>(null)
  const [endedAt, setEndedAt] = useState<number | null>(null)
  const [stats, setStats] = useState<StreamStats>(EMPTY_STATS)
  const [networkOffline, setNetworkOffline] = useState(() => typeof navigator !== 'undefined' && navigator.onLine === false)
  const sendRef = useRef<(message: object) => boolean>(() => false)
  const endedRef = useRef(false)

  useEffect(() => {
    if (!sessionId) return
    const id = sessionId
    window.clearTimeout(pendingStops.get(id))
    pendingStops.delete(id)

    let disposed = false
    let socket: WebSocket | null = null
    let pc: RTCPeerConnection | null = null
    let iceServers: RTCIceServer[] = []
    let socketAttempts = 0
    let everLive = false
    let reconnectTimer: number | undefined
    let disconnectTimer: number | undefined
    let statsTimer: number | undefined
    let last = { at: 0, bytes: 0, lost: 0, received: 0 }
    endedRef.current = false

    const send = (message: object): boolean => {
      if (socket?.readyState !== WebSocket.OPEN) return false
      socket.send(JSON.stringify(message))
      return true
    }
    sendRef.current = send

    const finish = (reason: string) => {
      if (endedRef.current) return
      endedRef.current = true
      setEndReason(reason)
      setEndedAt(Date.now())
      setPhase('ended')
      closePeer()
      socket?.close(1000)
    }

    function closePeer() {
      window.clearTimeout(disconnectTimer)
      window.clearInterval(statsTimer)
      if (pc) {
        pc.ontrack = pc.onicecandidate = pc.onconnectionstatechange = null
        pc.close()
        pc = null
      }
    }

    async function sampleStats(peer: RTCPeerConnection) {
      const report = await peer.getStats()
      let rtt: number | null = null
      let inbound: RTCInboundRtpStreamStats | undefined
      report.forEach((entry: RTCStats) => {
        if (entry.type === 'inbound-rtp' && (entry as RTCInboundRtpStreamStats).kind === 'video') {
          inbound = entry as RTCInboundRtpStreamStats
        }
        const pair = entry as RTCIceCandidatePairStats
        if (entry.type === 'candidate-pair' && pair.nominated && pair.state === 'succeeded' && pair.currentRoundTripTime !== undefined) {
          rtt = Math.round(pair.currentRoundTripTime * 1000)
        }
      })
      if (!inbound) return
      const now = performance.now()
      const bytes = inbound.bytesReceived ?? 0
      const lost = Math.max(0, inbound.packetsLost ?? 0)
      const received = inbound.packetsReceived ?? 0
      const dt = (now - last.at) / 1000
      const kbps = last.at && dt > 0 ? Math.round(((bytes - last.bytes) * 8) / 1000 / dt) : null
      const dLost = lost - last.lost
      const dTotal = dLost + (received - last.received)
      const lossPct = last.at && dTotal > 0 ? Math.round((1000 * dLost) / dTotal) / 10 : null
      last = { at: now, bytes, lost, received }
      const next = {
        rttMs: rtt,
        lossPct,
        fps: inbound.framesPerSecond !== undefined ? Math.round(inbound.framesPerSecond) : null,
        kbps,
        width: inbound.frameWidth ?? null,
        height: inbound.frameHeight ?? null,
      }
      if (!disposed) setStats({ ...next, quality: qualityOf(next) })
    }

    async function negotiate() {
      if (disposed || endedRef.current) return
      closePeer()
      setPhase(everLive ? 'reconnecting' : 'negotiating')
      const peer = new RTCPeerConnection({ iceServers })
      pc = peer
      last = { at: 0, bytes: 0, lost: 0, received: 0 }
      peer.addTransceiver('video', { direction: 'recvonly' })
      peer.ontrack = (event) => {
        const video = videoRef.current
        if (video) {
          video.srcObject = event.streams[0] ?? new MediaStream([event.track])
          void video.play().catch(() => undefined)
        }
      }
      peer.onicecandidate = (event) =>
        send({
          type: 'candidate',
          candidate: event.candidate ? event.candidate.toJSON() : null,
        })
      peer.onconnectionstatechange = () => {
        if (pc !== peer) return
        const state = peer.connectionState
        if (state === 'connected') {
          window.clearTimeout(disconnectTimer)
          everLive = true
          setPhase('live')
          setConnectedAt((at) => at ?? Date.now())
          send({ type: 'state', state })
          window.clearInterval(statsTimer)
          statsTimer = window.setInterval(() => void sampleStats(peer).catch(() => undefined), 1000)
        } else if (state === 'failed') {
          send({ type: 'state', state })
          void negotiate()
        } else if (state === 'disconnected') {
          setPhase('reconnecting')
          disconnectTimer = window.setTimeout(() => {
            if (pc === peer && peer.connectionState !== 'connected') {
              send({ type: 'state', state: 'disconnected' })
              void negotiate()
            }
          }, DISCONNECTED_GRACE_MS)
        }
      }
      const offer = await peer.createOffer()
      await peer.setLocalDescription(offer)
      if (pc === peer) send({ type: 'offer', sdp: offer.sdp })
    }

    async function onMessage(raw: string) {
      let message: { type: string; [key: string]: unknown }
      try {
        message = JSON.parse(raw) as typeof message
      } catch {
        return
      }
      switch (message.type) {
        case 'ready':
          socketAttempts = 0
          iceServers = (message.ice_servers as RTCIceServer[]) ?? []
          setAgentOnline(Boolean(message.agent_online))
          if (message.agent_online) await negotiate()
          else setPhase('waiting')
          break
        case 'answer':
          await pc?.setRemoteDescription({ type: 'answer', sdp: String(message.sdp) }).catch(() => undefined)
          break
        case 'candidate':
          if (message.candidate) await pc?.addIceCandidate(message.candidate as RTCIceCandidateInit).catch(() => undefined)
          break
        case 'peer_left':
          setAgentOnline(false)
          closePeer()
          setPhase(everLive ? 'reconnecting' : 'waiting')
          break
        case 'peer_ready':
          setAgentOnline(true)
          await negotiate()
          break
        case 'ended':
          finish(String(message.reason ?? 'ended'))
          break
      }
    }

    async function connect(refresh: boolean) {
      if (disposed || endedRef.current) return
      let token = useAuthStore.getState().accessToken
      if (refresh || !token) token = (await refreshSession())?.access_token ?? null
      if (!token) return finish('signed_out')
      const ws = new WebSocket(socketUrl(id), socketProtocols(token))
      socket = ws
      ws.onmessage = (event) => void onMessage(String(event.data))
      ws.onclose = (event) => {
        if (socket !== ws || disposed || endedRef.current) return
        if (event.code === 4404) return finish('not_available')
        if (event.code === 4403) return finish('forbidden')
        setPhase('reconnecting')
        if (!navigator.onLine) return // wait for the 'online' event rather than burning attempts
        socketAttempts += 1
        if (socketAttempts > MAX_SOCKET_ATTEMPTS) return finish('connection_lost')
        const delay = Math.min(8000, 500 * 2 ** socketAttempts)
        reconnectTimer = window.setTimeout(() => void connect(event.code === 4401), delay)
      }
    }

    /** Back online or on a different network: recover now instead of waiting for timeouts. */
    function recover() {
      if (disposed || endedRef.current) return
      if (socket?.readyState === WebSocket.OPEN) {
        if (everLive) send({ type: 'state', state: 'disconnected' }) // recorded as an interruption + reconnect
        if (everLive || pc) void negotiate()
        return
      }
      if (socket?.readyState === WebSocket.CONNECTING) return
      window.clearTimeout(reconnectTimer)
      socketAttempts = 0
      void connect(false)
    }
    const onOffline = () => {
      setNetworkOffline(true)
      if (!endedRef.current) setPhase('reconnecting')
    }
    const onOnline = () => {
      setNetworkOffline(false)
      recover()
    }
    const onNetworkChange = () => {
      if (navigator.onLine && everLive) recover()
    }
    window.addEventListener('offline', onOffline)
    window.addEventListener('online', onOnline)
    const connection = networkConnection()
    connection?.addEventListener('change', onNetworkChange)

    void connect(false)

    return () => {
      disposed = true
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('online', onOnline)
      connection?.removeEventListener('change', onNetworkChange)
      window.clearTimeout(reconnectTimer)
      closePeer()
      socket?.close(1000)
      sendRef.current = () => false
      if (!endedRef.current) {
        // Navigating away ends the stream (a reload reconnects within the server's grace period instead).
        pendingStops.set(
          id,
          window.setTimeout(() => {
            pendingStops.delete(id)
            void api.post(`/live/sessions/${id}/stop`).catch(() => undefined)
          }, STOP_DELAY_MS),
        )
      }
    }
  }, [sessionId, videoRef])

  const stop = useCallback(() => {
    if (!sendRef.current({ type: 'stop' }) && sessionId) {
      void api.post(`/live/sessions/${sessionId}/stop`).catch(() => undefined)
      endedRef.current = true
      setEndReason('viewer_stopped')
      setEndedAt(Date.now())
      setPhase('ended')
    }
  }, [sessionId])

  return {
    phase,
    endReason,
    agentOnline,
    networkOffline,
    connectedAt,
    endedAt,
    stats,
    stop,
  }
}
