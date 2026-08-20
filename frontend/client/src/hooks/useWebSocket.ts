// The run timeline is delivered through authenticated, resumable SSE. A second
// cross-origin WebSocket adds no event coverage and cannot reliably carry an
// HttpOnly third-party session cookie in privacy-restricted browsers.
import { useMemo } from 'react'
import type { AgentEvent, SocketState } from '../types'

export function useWebSocket(_onEvent?: (event: AgentEvent) => void) {
  return useMemo<SocketState & { send: (payload: unknown) => void }>(() => ({
    connected: true,
    send: () => undefined,
  }), [])
}
