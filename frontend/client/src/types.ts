// Dark Mission Control: shared domain types for the chat rail, execution timeline, and task graph.

export type AgentStage = 'planning' | 'executing' | 'review' | 'completed' | 'error' | 'idle'
export type EventKind = 'plan' | 'tool' | 'review' | 'answer' | 'system' | 'error'

export interface PlanStep {
  id: string
  title: string
  description?: string
  depends_on?: string[]
  status?: 'pending' | 'active' | 'completed' | 'error'
  tool?: string
}

export interface AgentPlan {
  goal: string
  steps: PlanStep[]
  acceptance_criteria: string[]
}

export interface AgentEvent {
  id?: string
  sequence?: number
  type?: EventKind | string
  kind?: EventKind | string
  message?: string
  content?: string
  text?: string
  step_id?: string
  stepId?: string
  status?: string
  timestamp?: string
  tool?: string
  payload?: Record<string, unknown>
  created_at?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string
  runId?: string
  stage?: AgentStage
}

export interface RunSubmission {
  run_id: string
  status: string
  task: string
}

export interface ChatResponse {
  run_id?: string
  status?: string
  answer?: string
  plan?: AgentPlan | PlanStep[] | string[]
  events?: AgentEvent[]
}

export interface SocketState {
  connected: boolean
  lastEvent?: AgentEvent
  error?: string
}
