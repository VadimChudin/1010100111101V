// Dark Mission Control: shared domain types for the chat rail, execution timeline, and task graph.

export type AgentStage = 'planning' | 'executing' | 'review' | 'completed' | 'error' | 'idle'
export type EventKind = 'plan' | 'tool' | 'review' | 'answer' | 'system' | 'error'
export type ApprovalMode = 'plan' | 'confirm_each' | 'allow_workspace_edits' | 'smart_development' | 'all_approvals_for_run'

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

export type ApprovalGrantScope = 'once' | 'run' | 'workspace' | 'all_approved_run'

export interface ApprovalRequest {
  id: string
  run_id: string
  action_type: string
  scope: Record<string, unknown>
  status: 'pending' | 'approved' | 'denied' | string
  requested_at: string
  decided_at?: string | null
  expires_at?: string | null
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


export type WorkspaceMarkerType = 'note' | 'task' | 'decision' | 'question' | 'error' | 'blocked' | 'running' | 'approval_required'
export type WorkspaceTaskStatus = 'backlog' | 'todo' | 'in_progress' | 'blocked' | 'done'

export interface WorkspaceProject {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
}

export interface WorkspaceModule {
  id: string
  project_id: string
  title: string
  kind: string
  source_scope: string
  aliases: string[]
  dependencies: string[]
  position_x: number
  position_y: number
  status: string
  created_at: string
  updated_at: string
}

export interface WorkspaceNote {
  id: string
  project_id: string
  module_id: string
  title: string
  content: string
  kind: WorkspaceMarkerType
  author: string
  source_run_id?: string
  created_at: string
}

export interface WorkspaceTask {
  id: string
  project_id: string
  module_id: string
  title: string
  description: string
  acceptance_criteria: string[]
  status: WorkspaceTaskStatus
  priority: 'low' | 'medium' | 'high' | 'critical'
  source_run_id?: string
  created_at: string
  updated_at: string
}

export interface WorkspaceMarker {
  id: string
  project_id: string
  module_id: string
  type: WorkspaceMarkerType
  title: string
  state: string
  source_kind: string
  source_id: string
  created_at: string
}

export interface WorkspaceSnapshot {
  project: WorkspaceProject
  modules: WorkspaceModule[]
  notes: WorkspaceNote[]
  tasks: WorkspaceTask[]
  markers: WorkspaceMarker[]
}


export interface AuthUser {
  id: string
  github_id: string
  login: string
  email?: string
  avatar_url?: string
  created_at: string
}

export interface AuthStatus {
  authenticated: boolean
  user?: AuthUser
  github_configured: boolean
}
