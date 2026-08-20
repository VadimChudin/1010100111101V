import { useCallback, useEffect, useState } from 'react'
import { Activity, ChevronRight, FolderGit2, MessageSquare, RefreshCw } from 'lucide-react'
import Chat from './components/Chat'
import TaskGraph from './components/TaskGraph'
import { useAuth } from './hooks/useAuth'
import { useChat } from './hooks/useChat'
import { useWorkspace } from './hooks/useWorkspace'
import { useWebSocket } from './hooks/useWebSocket'
import type { WorkspaceSnapshot, WorkspaceTaskStatus } from './types'

type WorkspaceView = 'chat' | 'project'

function ServiceIndicator({ healthy, socketConnected, serenaReady, runtimeOnline }: { healthy: boolean | null; socketConnected: boolean; serenaReady: boolean | null; runtimeOnline: boolean }) {
  const [open, setOpen] = useState(false)
  const hasIssue = healthy === false || !socketConnected
  const label = hasIssue ? 'Attention needed' : 'System ready'

  return <div className="relative">
    <button type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 py-2 text-left transition-colors hover:border-white/20 hover:bg-white/[0.06]">
      <span className={`h-2 w-2 rounded-full ${hasIssue ? 'bg-rose-400 shadow-[0_0_0_4px_rgba(251,113,133,.11)]' : 'bg-emerald-400 shadow-[0_0_0_4px_rgba(52,211,153,.11)]'}`} />
      <span className="hidden font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim sm:inline">{label}</span>
    </button>
    {open && <section className="absolute right-0 top-[calc(100%+10px)] z-50 w-[296px] overflow-hidden rounded-2xl border border-white/10 bg-[#17191e]/95 p-4 shadow-2xl backdrop-blur-xl">
      <p className="font-mono text-[9px] uppercase tracking-[0.15em] text-signal-ice">Local system</p>
      <div className="mt-3 space-y-2.5">
        {[
          ['Cloud session', socketConnected ? 'Connected' : 'Reconnecting', socketConnected],
          ['Local runtime', runtimeOnline ? 'Running' : 'Waiting for device', runtimeOnline],
          ['Serena context', serenaReady ? 'Ready' : 'Preparing', Boolean(serenaReady)],
          ['Graphiti memory', 'Optional background profile', true],
        ].map(([name, detail, okay]) => <div key={String(name)} className="flex items-center justify-between gap-3 text-xs"><span className="text-white/80">{name}</span><span className={`flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] ${okay ? 'text-emerald-300' : 'text-amber-300'}`}><span className={`h-1.5 w-1.5 rounded-full ${okay ? 'bg-emerald-400' : 'bg-amber-300'}`} />{detail}</span></div>)}
      </div>
      {hasIssue && <p className="mt-4 border-t border-white/[0.08] pt-3 text-xs leading-5 text-rose-200">The cloud connection needs attention. Project data remains local and the chat will reconnect automatically.</p>}
    </section>}
  </div>
}

const TASK_META: Record<string, { label: string; className: string; next?: WorkspaceTaskStatus; action?: string }> = {
  clarifying: { label: 'Clarifying', className: 'text-amber-200 bg-amber-300/[0.11]', next: 'ready', action: 'Mark ready' },
  ready: { label: 'Ready', className: 'text-signal-ice bg-signal-ice/[0.1]', next: 'working', action: 'Start work' },
  working: { label: 'Working', className: 'text-violet-200 bg-violet-300/[0.12]', next: 'review', action: 'Send to review' },
  needs_you: { label: 'Needs you', className: 'text-amber-200 bg-amber-300/[0.11]' },
  review: { label: 'Review', className: 'text-signal-ice bg-signal-ice/[0.1]', next: 'done', action: 'Archive complete' },
  deferred: { label: 'Deferred', className: 'text-text-dim bg-white/[0.06]', next: 'clarifying', action: 'Resume' },
  todo: { label: 'Clarifying', className: 'text-amber-200 bg-amber-300/[0.11]', next: 'ready', action: 'Mark ready' },
  in_progress: { label: 'Working', className: 'text-violet-200 bg-violet-300/[0.12]', next: 'review', action: 'Send to review' },
  backlog: { label: 'Deferred', className: 'text-text-dim bg-white/[0.06]', next: 'clarifying', action: 'Resume' },
  blocked: { label: 'Needs you', className: 'text-amber-200 bg-amber-300/[0.11]' },
}

function ProjectAside({ workspace, repository, files, indexing, onIndex, onTaskStatus }: { workspace?: WorkspaceSnapshot; repository: ReturnType<typeof useWorkspace>['repository']; files: ReturnType<typeof useWorkspace>['files']; indexing: boolean; onIndex: () => void; onTaskStatus: (taskId: string, status: WorkspaceTaskStatus) => Promise<void> }) {
  const [expandedTask, setExpandedTask] = useState<string>()
  const [archiveOpen, setArchiveOpen] = useState(false)
  const activeTasks = workspace?.tasks.filter((task) => task.status !== 'done') || []
  const completedTasks = workspace?.tasks.filter((task) => task.status === 'done') || []
  const dependencies = repository?.dependencies.slice(0, 5) || []
  const moduleName = (moduleId: string) => workspace?.modules.find((module) => module.id === moduleId)?.title || 'Project'
  return <aside className="hidden w-[314px] shrink-0 border-l border-white/[0.08] bg-[#111318]/88 xl:flex xl:flex-col">
    <div className="border-b border-white/[0.08] px-5 py-5"><p className="font-mono text-[9px] uppercase tracking-[0.15em] text-signal-ice">Project work</p><div className="mt-2 flex items-center justify-between gap-3"><h2 className="truncate text-base font-semibold tracking-[-0.03em] text-white">{workspace?.project.name || 'Project map'}</h2><span className="rounded-full bg-white/[0.07] px-2 py-0.5 font-mono text-[9px] text-white/70">{activeTasks.length}</span></div><p className="mt-1 text-xs leading-5 text-text-dim">Tasks attach to project modules and stay on the same canvas.</p><button type="button" onClick={onIndex} disabled={indexing} className="mt-4 inline-flex items-center gap-2 rounded-lg border border-signal-ice/25 bg-signal-ice/[0.08] px-3 py-2 font-mono text-[9px] uppercase tracking-[0.12em] text-signal-ice transition-colors hover:bg-signal-ice/[0.14] disabled:opacity-50"><RefreshCw size={12} className={indexing ? 'animate-spin' : ''} />{indexing ? 'Refreshing map' : 'Refresh project map'}</button></div>
    <div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-5"><section className="space-y-2">{activeTasks.length ? activeTasks.map((task) => { const meta = TASK_META[task.status] || TASK_META.clarifying; const open = expandedTask === task.id; return <article key={task.id} className={`rounded-xl border transition-colors ${open ? 'border-signal-ice/30 bg-signal-ice/[0.055]' : 'border-white/[0.08] bg-white/[0.025]'}`}><button type="button" onClick={() => setExpandedTask(open ? undefined : task.id)} className="w-full p-3 text-left"><div className="flex items-start justify-between gap-2"><p className="line-clamp-2 text-xs font-medium leading-5 text-white/90">{task.title}</p><ChevronRight size={14} className={`mt-1 shrink-0 text-text-dim transition-transform ${open ? 'rotate-90' : ''}`} /></div><div className="mt-2 flex items-center justify-between gap-2"><span className={`rounded-full px-2 py-0.5 font-mono text-[8px] uppercase tracking-[0.1em] ${meta.className}`}>{meta.label}</span><span className="max-w-[110px] truncate font-mono text-[8px] uppercase tracking-[0.08em] text-text-dim">{moduleName(task.module_id)}</span></div></button>{open && <div className="border-t border-white/[0.08] px-3 pb-3 pt-3"><p className="text-[11px] leading-5 text-text-muted">{task.description || 'The task is waiting for more context, a decision, or an implementation request.'}</p>{task.acceptance_criteria.length > 0 && <div className="mt-3"><p className="font-mono text-[8px] uppercase tracking-[0.12em] text-text-dim">Acceptance</p><ul className="mt-1.5 space-y-1 text-[10px] leading-4 text-white/70">{task.acceptance_criteria.map((criterion) => <li key={criterion}>• {criterion}</li>)}</ul></div>}<div className="mt-3 grid grid-cols-2 gap-2"><span className="rounded-lg border border-white/[0.08] px-2 py-1.5 font-mono text-[8px] uppercase tracking-[0.08em] text-text-dim">Diff · pending</span><span className="rounded-lg border border-white/[0.08] px-2 py-1.5 font-mono text-[8px] uppercase tracking-[0.08em] text-text-dim">Log · hidden</span></div>{meta.next && <button type="button" onClick={() => void onTaskStatus(task.id, meta.next!)} className="mt-3 w-full rounded-lg border border-signal-ice/25 bg-signal-ice/[0.08] px-3 py-2 font-mono text-[9px] uppercase tracking-[0.1em] text-signal-ice transition-colors hover:bg-signal-ice/[0.14]">{meta.action}</button>}</div>}</article> }) : <p className="rounded-xl border border-dashed border-white/[0.1] p-3 text-xs leading-5 text-text-dim">Project requests and pinned file notes will form a calm work queue here.</p>}</section>
      <section className="mt-6 border-t border-white/[0.08] pt-5"><button type="button" onClick={() => setArchiveOpen((value) => !value)} className="flex w-full items-center justify-between font-mono text-[9px] uppercase tracking-[0.13em] text-text-dim"><span>Cold archive · {completedTasks.length}</span><ChevronRight size={12} className={archiveOpen ? 'rotate-90 transition-transform' : 'transition-transform'} /></button>{archiveOpen && <div className="mt-3 space-y-1.5">{completedTasks.length ? completedTasks.map((task) => <div key={task.id} className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-2.5 py-2 text-xs text-text-dim line-through">{task.title}</div>) : <p className="text-xs leading-5 text-text-dim">Completed work will collect here.</p>}</div>}</section>
      <section className="mt-6 border-t border-white/[0.08] pt-5"><p className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-dim">Repository</p><div className="mt-3 space-y-2 text-xs"><div className="flex justify-between gap-4"><span className="text-text-dim">Tracked files</span><span className="font-mono text-white/75">{repository?.files_count ?? files.filter((file) => file.kind === 'file').length}</span></div><div className="flex justify-between gap-4"><span className="text-text-dim">Modules</span><span className="font-mono text-white/75">{repository?.modules_count ?? workspace?.modules.length ?? 0}</span></div></div></section>
      <section className="mt-6 border-t border-white/[0.08] pt-5"><p className="font-mono text-[9px] uppercase tracking-[0.14em] text-text-dim">Key dependencies</p><div className="mt-3 space-y-2">{dependencies.length ? dependencies.map((dependency) => <div key={`${dependency.ecosystem}-${dependency.name}`} className="flex items-center justify-between gap-3 font-mono text-[10px]"><span className="truncate text-white/70">{dependency.name}</span><span className="text-text-dim">{dependency.version}</span></div>) : <p className="text-xs leading-5 text-text-dim">Index the project to reveal dependencies.</p>}</div></section>
    </div>
  </aside>
}

export default function App() {
  const [view, setView] = useState<WorkspaceView>('chat')
  const [apiHealthy, setApiHealthy] = useState<boolean | null>(null)
  const [serenaReady, setSerenaReady] = useState<boolean | null>(null)
  const auth = useAuth()
  const chat = useChat()
  const workspace = useWorkspace()
  const socket = useWebSocket(chat.appendEvent)

  const checkHealth = useCallback(async () => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app'
      const response = await fetch(`${apiUrl.replace(/\/$/, '')}/v1/healthz`)
      setApiHealthy(response.ok)
    } catch {
      setApiHealthy(false)
    }
  }, [])

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app'
    void fetch(`${apiUrl.replace(/\/$/, '')}/v1/serena/status`)
      .then(async (response) => response.ok ? response.json() as Promise<{ available?: boolean }> : Promise.reject())
      .then((status) => setSerenaReady(Boolean(status.available)))
      .catch(() => setSerenaReady(false))
    void checkHealth()
  }, [checkHealth])

  const projectName = workspace.workspace?.project.name || workspace.repository?.repository_url?.split('/').pop()?.replace(/\.git$/, '') || 'Agent Room'
  const runtimeOnline = workspace.devices.some((device) => device.status === 'online')
  const tabClass = (active: boolean) => `group relative flex h-11 w-11 items-center justify-center rounded-xl transition-colors ${active ? 'bg-signal-ice/[0.12] text-signal-ice' : 'text-text-dim hover:bg-white/[0.055] hover:text-white'}`

  return <div className="min-h-screen bg-[#0b0d10] text-[#f5f1e8] selection:bg-signal-ice/30">
    <header className="relative z-30 flex h-[66px] items-center justify-between border-b border-white/[0.08] bg-[#101216]/90 px-4 backdrop-blur-xl sm:px-6">
      <div className="flex min-w-0 items-center gap-3"><div className="logo-mark"><span /></div><div className="min-w-0"><p className="truncate text-sm font-semibold tracking-[-0.035em] text-white">{projectName}</p><p className="hidden font-mono text-[8px] uppercase tracking-[0.15em] text-text-dim sm:block">Agent Room · local project intelligence</p></div></div>
      <div className="flex items-center gap-2"><ServiceIndicator healthy={apiHealthy} socketConnected={socket.connected} serenaReady={serenaReady} runtimeOnline={runtimeOnline} /><button type="button" onClick={auth.status?.authenticated ? () => void auth.logout() : auth.login} disabled={!auth.loading && !auth.status?.authenticated && !auth.status?.github_configured} className="hidden rounded-full border border-white/10 bg-white/[0.035] px-3 py-2 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim transition-colors hover:border-white/20 hover:text-white disabled:opacity-50 sm:block">{auth.loading ? 'Identity…' : auth.status?.authenticated ? auth.status.user?.login || 'Connected' : 'Connect GitHub'}</button></div>
    </header>
    <div className="flex min-h-[calc(100vh-66px)]">
      <nav aria-label="Main workspace" className="z-20 flex w-[68px] shrink-0 flex-col items-center border-r border-white/[0.08] bg-[#101216]/72 py-4 backdrop-blur-xl">
        <div className="flex flex-col gap-2"><button type="button" title="Chat" aria-label="Chat" onClick={() => setView('chat')} className={tabClass(view === 'chat')}><MessageSquare size={18} strokeWidth={1.8} />{view === 'chat' && <span className="absolute -left-px h-5 w-0.5 rounded-full bg-signal-ice" />}</button><button type="button" title="Project" aria-label="Project" onClick={() => setView('project')} className={tabClass(view === 'project')}><FolderGit2 size={18} strokeWidth={1.8} />{view === 'project' && <span className="absolute -left-px h-5 w-0.5 rounded-full bg-signal-ice" />}</button></div>
        <div className="mt-auto pb-2"><button type="button" onClick={checkHealth} title="Refresh system status" className="grid h-9 w-9 place-items-center rounded-xl text-text-dim transition-colors hover:bg-white/[0.055] hover:text-white"><Activity size={16} /></button></div>
      </nav>
      {view === 'chat' ? <main className="relative flex min-w-0 flex-1 justify-center overflow-hidden bg-[radial-gradient(circle_at_50%_-20%,rgba(157,232,255,.075),transparent_38rem)]"><div className="absolute inset-0 opacity-[0.24] [background-image:linear-gradient(rgba(255,255,255,.022)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.022)_1px,transparent_1px)] [background-size:42px_42px]" /><div className="relative flex w-full max-w-[920px] min-w-0"><Chat messages={chat.messages} plan={chat.plan} events={chat.events} approvals={chat.approvals} loading={chat.loading} error={chat.error} stage={chat.stage} connected={socket.connected} runId={chat.runId} moduleTitle={workspace.selectedModule?.title} onSend={chat.sendMessage} onApprovalDecision={chat.decideApproval} onCaptureNote={async (runId, title, content) => { const target = workspace.selectedModule || workspace.workspace?.modules[0]; if (!target) throw new Error('Index the project before saving context.'); await workspace.createNote(target, title, content, runId) }} onCaptureTask={async (runId, title, description) => { const target = workspace.selectedModule || workspace.workspace?.modules[0]; if (!target) throw new Error('Index the project before creating a task.'); await workspace.createTask(target, title, description, runId) }} approvalMode={chat.approvalMode} onApprovalModeChange={chat.setApprovalMode} /></div></main> : <main className="flex min-w-0 flex-1 overflow-hidden bg-[#0d0f13]"><section className="relative min-w-0 flex-1"><TaskGraph plan={chat.plan} events={chat.events} connected={socket.connected} workspace={workspace.workspace} repository={workspace.repository} files={workspace.files} indexing={workspace.indexing} selectedModuleId={workspace.selectedModuleId} onSelectModule={workspace.setSelectedModuleId} onIndexRepository={() => void workspace.indexRepository()} /></section><ProjectAside workspace={workspace.workspace} repository={workspace.repository} files={workspace.files} indexing={workspace.indexing} onIndex={() => void workspace.indexRepository()} onTaskStatus={workspace.updateTaskStatus} /></main>}
    </div>
  </div>
}
