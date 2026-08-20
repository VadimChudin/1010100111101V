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
  mode?: 'chat' | 'project'
  answer?: string
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
export type WorkspaceTaskStatus = 'backlog' | 'todo' | 'in_progress' | 'blocked' | 'done' | 'clarifying' | 'ready' | 'working' | 'needs_you' | 'review' | 'deferred'

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
  origin: 'git' | 'manual' | string
  created_at: string
  updated_at: string
}

export interface RepositoryFile {
  path: string
  kind: 'file' | 'directory'
  language?: string | null
  size?: number | null
}

export interface RepositoryDependency {
  name: string
  ecosystem: 'python' | 'node'
  version: string
  group: string
}

export interface RepositoryIndex {
  project_id: string
  repository_url: string
  branch: string
  commit_sha: string
  indexed_at: string
  files_count: number
  modules_count: number
  dependencies: RepositoryDependency[]
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


export type DeviceStatus = 'online' | 'offline' | 'revoked'

export interface LocalRepositoryInventory {
  repository_url: string
  branch: string
  commit_sha: string
  dirty: boolean
  tracked_files: number
  workspace_fingerprint: string
}

export interface ProjectDevice {
  id: string
  project_id: string
  owner_user_id: string
  name: string
  status: DeviceStatus
  runtime_version: string
  capabilities: string[]
  inventory?: LocalRepositoryInventory | null
  last_seen_at?: string | null
  last_synced_at?: string | null
  created_at: string
  revoked_at?: string | null
}

export interface GraphitiEpisodeEnvelope {
  episode_id: string
  group_id: string
  name: string
  content: string
  source: string
  source_run_id?: string | null
  source_commit_sha?: string | null
  occurred_at: string
}


export type DeviceJobType = 'find_symbol' | 'find_references' | 'index_workspace' | 'retrieve_project_memory' | 'refresh_workspace_index' | 'list_workspace_files' | 'search_workspace_text' | 'read_file_range' | 'apply_unified_patch' | 'run_test_profile' | 'git_status' | 'git_diff' | 'git_commit' | 'git_push'
export type DeviceJobStatus = 'pending_approval' | 'queued' | 'leased' | 'completed' | 'failed' | 'expired' | 'cancelled'

export interface DeviceJob {
  id: string
  project_id: string
  device_id: string
  creator_user_id: string
  type: DeviceJobType
  payload: Record<string, unknown>
  status: DeviceJobStatus
  expires_at: string
  approved_at?: string | null
  approved_by_user_id?: string | null
  lease_expires_at?: string | null
  result?: Record<string, unknown> | null
  error?: string | null
  created_at: string
  completed_at?: string | null
}


export type ProjectSourceKind = 'paired_local' | 'github_repository'

export interface LocalWorkspace {
  id: string
  project_id: string
  device_id: string
  display_name: string
  workspace_key: string
  inventory: LocalRepositoryInventory
  index_revision: number
  indexed_at: string
  created_at: string
  updated_at: string
}

export interface ProjectSource {
  project_id: string
  kind: ProjectSourceKind
  local_workspace_id?: string | null
  repository_url?: string | null
  ref?: string | null
  selected_at: string
  selected_by_user_id?: string | null
}
