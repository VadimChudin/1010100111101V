// Dark Mission Control: chat state translates durable agent runs into a readable operator narrative.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AgentEvent, AgentPlan, AgentStage, ApprovalGrantScope, ApprovalMode, ApprovalRequest, ChatMessage, ChatResponse, PlanStep, RunSubmission } from '../types'

const initialMessage: ChatMessage = {
  id: 'intro',
  role: 'assistant',
  content: 'Здравствуйте. Я помогу разобраться с проектом, обсудить идею или подготовить работу над кодом — в удобном для вас темпе.',
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

const eventMessage = (event: AgentEvent): string => {
  const payload = event.payload || {}
  if (typeof payload.message === 'string') return payload.message
  if (event.type === 'plan.created') return 'Plan generated and ready for execution.'
  if (event.type === 'run.created') return 'Run policy recorded.'
  if (event.type === 'run.started') return 'Run started.'
  if (event.type === 'tool.result') return 'Tool execution stage completed.'
  if (event.type === 'approval.requested') return `Approval required for ${typeof payload.tool === 'string' ? payload.tool : 'a protected action'}.`
  if (event.type === 'approval.granted') return 'Approval granted and the authorised action is executing.'
  if (event.type === 'approval.denied') return 'Approval denied. The protected action was not executed.'
  if (event.type === 'review.updated') return typeof payload.comment === 'string' ? payload.comment : 'Review completed.'
  if (event.type === 'run.completed') return 'Run completed.'
  if (event.type === 'run.failed') return 'Run failed.'
  return event.message || event.content || event.text || 'Agent event received.'
}

const normalizeTimelineEvent = (event: AgentEvent): AgentEvent => {
  const payload = event.payload || {}
  return {
    ...event,
    ...payload,
    id: event.id || (event.sequence ? `event-${event.sequence}` : undefined),
    message: eventMessage(event),
    timestamp: event.created_at || event.timestamp,
  }
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([initialMessage])
  const [plan, setPlan] = useState<PlanStep[]>([])
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [runId, setRunId] = useState<string>()
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>()
  const [approvalMode, setApprovalMode] = useState<ApprovalMode>('confirm_each')
  const streamRef = useRef<EventSource | null>(null)
  const terminalRef = useRef(false)

  const apiUrl = import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app'

  const closeStream = useCallback(() => {
    streamRef.current?.close()
    streamRef.current = null
  }, [])

  useEffect(() => () => closeStream(), [closeStream])

  const refreshApprovals = useCallback(async (targetRunId?: string) => {
    if (!targetRunId) return
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, '')}/v1/runs/${targetRunId}/approvals?status=pending`, { credentials: 'include' })
      if (!response.ok) throw new Error(`Approval request failed with ${response.status}`)
      const data = await response.json() as { approvals?: ApprovalRequest[] }
      setApprovals(Array.isArray(data.approvals) ? data.approvals : [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load pending approvals.')
    }
  }, [apiUrl])

  const appendEvent = useCallback((rawEvent: AgentEvent) => {
    const event = normalizeTimelineEvent(rawEvent)
    setEvents((current) => {
      if (event.sequence && current.some((item) => item.sequence === event.sequence)) return current
      return [...current.slice(-39), event]
    })

    const payload = event.payload || {}
    if (event.type === 'plan.created' && Array.isArray(payload.steps)) setPlan(normalizePlan(payload as unknown as AgentPlan))
    const stepId = event.step_id || event.stepId
    if (stepId) setPlan((current) => current.map((step) => step.id === stepId ? { ...step, status: event.status === 'completed' ? 'completed' : 'active' } : step))

    if (event.type === 'run.completed') {
      terminalRef.current = true
      setLoading(false)
      setApprovals([])
      closeStream()
      const review = payload.review as Record<string, unknown> | undefined
      const answer = typeof review?.comment === 'string' ? review.comment : 'Run completed. Review the timeline for details.'
      setMessages((current) => [...current, { id: `assistant-${Date.now()}`, role: 'assistant', content: answer, timestamp: new Date().toISOString(), runId, stage: 'completed' }])
    }
    if (event.type === 'run.failed') {
      terminalRef.current = true
      setLoading(false)
      setApprovals([])
      closeStream()
      setError(typeof payload.message === 'string' ? payload.message : 'The agent run failed.')
    }
  }, [closeStream, runId])

  useEffect(() => {
    if (!runId || !loading) return
    void refreshApprovals(runId)
    const interval = window.setInterval(() => void refreshApprovals(runId), 2000)
    return () => window.clearInterval(interval)
  }, [loading, refreshApprovals, runId])

  const decideApproval = useCallback(async (approvalId: string, approved: boolean, grantScope: ApprovalGrantScope) => {
    if (!runId) return
    setError(undefined)
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, '')}/v1/runs/${runId}/approvals/${approvalId}/decision`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, grant_scope: grantScope }),
      })
      if (!response.ok) throw new Error(`Approval decision failed with ${response.status}`)
      await refreshApprovals(runId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit the approval decision.')
    }
  }, [apiUrl, refreshApprovals, runId])

  const sendMessage = useCallback(async (text: string) => {
    const message = text.trim()
    if (!message || loading) return
    closeStream()
    terminalRef.current = false
    setError(undefined)
    setLoading(true)
    setPlan([])
    setEvents([])
    setApprovals([])
    setMessages((current) => [...current, { id: `user-${Date.now()}`, role: 'user', content: message, timestamp: new Date().toISOString() }])
    try {
      const response = await fetch(`${apiUrl.replace(/\/$/, '')}/v1/runs`, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message, approval_mode: approvalMode }) })
      if (!response.ok) throw new Error(`Request failed with ${response.status}`)
      const data = await response.json() as RunSubmission & { mode?: 'chat' | 'project' }
      setRunId(data.run_id)
      if (data.mode === 'project') {
        setMessages((current) => [...current, { id: `project-${Date.now()}`, role: 'assistant', content: 'Понял. Сначала соберу контекст и уточню важные детали, затем предложу следующий шаг.', timestamp: new Date().toISOString(), runId: data.run_id, stage: 'planning' }])
      }

      const source = new EventSource(`${apiUrl.replace(/\/$/, '')}/v1/runs/${data.run_id}/stream`, { withCredentials: true })
      source.addEventListener('timeline', (transportEvent) => {
        try {
          appendEvent(JSON.parse((transportEvent as MessageEvent).data) as AgentEvent)
        } catch {
          setError('Received an unreadable timeline event.')
        }
      })
      source.onerror = () => {
        if (!terminalRef.current && source.readyState === EventSource.CLOSED) {
          setError('The live timeline disconnected. Reopen the run to resume from its saved history.')
          setLoading(false)
        }
      }
      streamRef.current = source
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reach the agent API')
      setMessages((current) => [...current, { id: `error-${Date.now()}`, role: 'system', content: 'The run could not be started. Check the API URL and try again.', timestamp: new Date().toISOString(), stage: 'error' }])
      setLoading(false)
    }
  }, [apiUrl, appendEvent, approvalMode, closeStream, loading])

  const stage = useMemo<AgentStage>(() => {
    if (error) return 'error'
    if (events.some((event) => event.type === 'run.completed')) return 'completed'
    if (events.some((event) => event.type === 'review.updated')) return 'review'
    if (loading && events.some((event) => event.type === 'plan.created')) return 'executing'
    if (loading) return 'planning'
    return 'idle'
  }, [error, events, loading])

  return { messages, plan, events, runId, approvals, loading, error, stage, approvalMode, setApprovalMode, sendMessage, appendEvent, decideApproval }
}
