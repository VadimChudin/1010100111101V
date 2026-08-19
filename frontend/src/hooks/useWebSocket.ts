// Dark Mission Control: transport layer keeps the live signal rail honest and resilient.
import { useCallback, useEffect, useRef, useState } from 'react'
import type { AgentEvent, SocketState } from '../types'

function normalizeEvent(raw: unknown): AgentEvent {
  if (typeof raw === 'string') return { type: 'system', message: raw, timestamp: new Date().toISOString() }
  if (raw && typeof raw === 'object') return raw as AgentEvent
  return { type: 'system', message: 'Unknown event received', timestamp: new Date().toISOString() }
}

export function useWebSocket(onEvent?: (event: AgentEvent) => void) {
  const [state, setState] = useState<SocketState>({ connected: false })
  const socketRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number | undefined>(undefined)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback(() => {
    const apiUrl = import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app'
    const wsUrl = apiUrl.replace(/^http/, 'ws').replace(/\/$/, '') + '/v1/ws'
    const socket = new WebSocket(wsUrl)
    socketRef.current = socket
    socket.onopen = () => setState({ connected: true })
    socket.onmessage = (message) => {
      try {
        const event = normalizeEvent(JSON.parse(message.data))
        setState((current) => ({ ...current, lastEvent: event, error: undefined }))
        onEventRef.current?.(event)
      } catch {
        const event = normalizeEvent(message.data)
        setState((current) => ({ ...current, lastEvent: event }))
        onEventRef.current?.(event)
      }
    }
    socket.onerror = () => setState((current) => ({ ...current, connected: false, error: 'Transport unavailable' }))
    socket.onclose = () => {
      setState((current) => ({ ...current, connected: false }))
      window.clearTimeout(reconnectRef.current)
      reconnectRef.current = window.setTimeout(connect, 2500)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      window.clearTimeout(reconnectRef.current)
      socketRef.current?.close()
    }
  }, [connect])

  return { ...state, send: (payload: unknown) => socketRef.current?.send(JSON.stringify(payload)) }
}
