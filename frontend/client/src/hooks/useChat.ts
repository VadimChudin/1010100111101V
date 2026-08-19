// Dark Mission Control: chat state translates API runs into a readable operator narrative.
import { useCallback, useMemo, useState } from 'react'
import type { AgentEvent, AgentPlan, AgentStage, ChatMessage, ChatResponse, PlanStep } from '../types'

const initialMessage: ChatMessage = {
  id: 'intro',
  role: 'assistant',
  content: 'Send a brief and I will turn it into a visible run. You will see the plan, tool calls, and review states as they happen.',
  timestamp: new Date().toISOString(),
  stage: 'idle',
}

const planSteps = (plan?: ChatResponse['plan']): Array<PlanStep | string> => {
  if (Array.isArray(plan)) return plan
  if (plan && typeof plan === 'object' && Array.isArray((plan as AgentPlan).steps)) return (plan as AgentPlan).steps
  return []
}

export const normalizePlan = (plan?: ChatResponse['plan']): PlanStep[] => planSteps(plan).map((step, index) =>
  typeof step === 'string'
    ? { id: `step-${index + 1}`, title: step, status: 'pending' }
    : {
        id: step.id || `step-${index + 1}`,
        title: step.title,
        description: step.description,
        depends_on: step.depends_on,
        status: step.status || 'pending',
        tool: step.tool,
      },
)

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([initialMessage])
  const [plan, setPlan] = useState<PlanStep[]>([])
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [runId, setRunId] = useState<string>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>()

  const apiUrl = import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app'

  const appendEvent = useCallback((event: AgentEvent) => {
    setEvents((current) => [...current.slice(-39), { ...event, id: event.id || `${Date.now()}-${current.length}` }])
    const stepId = event.step_id || event.stepId
    if (stepId) setPlan((current) => current.map((step) => step.id === stepId ? { ...step, status: event.status === 'completed' ? 'completed' : 'active' } : step))
  }, [])

  const sendMessage = useCallback(async (text: string) => {
    const message = text.trim()
    if (!message || loading) return
    setError(undefined)
    setLoading(true)
    setMessages((current) => [...current, { id: `user-${Date.now()}`, role: 'user', content: message, timestamp: new Date().toISOString() }])
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, '')}/v1/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) })
      if (!response.ok) throw new Error(`Request failed with ${response.status}`)
      const data = await response.json() as ChatResponse
      setRunId(data.run_id)
      setPlan(normalizePlan(data.plan))
      ;(data.events || []).forEach(appendEvent)
      setMessages((current) => [...current, { id: `assistant-${Date.now()}`, role: 'assistant', content: data.answer || 'Run accepted. Watch the execution rail for updates.', timestamp: new Date().toISOString(), runId: data.run_id, stage: data.status === 'completed' ? 'completed' : 'executing' }])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach the agent API')
      setMessages((current) => [...current, { id: `error-${Date.now()}`, role: 'system', content: 'The run could not be started. Check the API URL and try again.', timestamp: new Date().toISOString(), stage: 'error' }])
    } finally {
      setLoading(false)
    }
  }, [apiUrl, appendEvent, loading])

  const stage = useMemo<AgentStage>(() => {
    if (error) return 'error'
    if (loading) return plan.length ? 'executing' : 'planning'
    if (events.some((event) => (event.type || event.kind) === 'review')) return 'review'
    return 'idle'
  }, [error, events, loading, plan.length])

  return { messages, plan, events, runId, loading, error, stage, sendMessage, appendEvent }
}
