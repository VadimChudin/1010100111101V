import { useCallback, useEffect, useState } from 'react'
import { Bot, CheckSquare2, ChevronRight, FolderGit2, Gauge, Library, ListTodo, Plus, Search, Settings2, Sparkles } from 'lucide-react'
import Chat from './components/Chat'
import TaskGraph from './components/TaskGraph'
import { useAuth } from './hooks/useAuth'
import { useChat } from './hooks/useChat'
import { useWorkspace } from './hooks/useWorkspace'
import { useWebSocket } from './hooks/useWebSocket'
import type { WorkspaceSnapshot, WorkspaceTaskStatus } from './types'

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const TASK_META: Record<string, { label: string; className: string; next?: WorkspaceTaskStatus; action?: string }> = {
  clarifying: { label: 'Clarifying', className: 'text-amber-200 bg-amber-300/[0.11]', next: 'ready', action: 'Ready' },
  ready: { label: 'Ready', className: 'text-signal-ice bg-signal-ice/[0.1]', next: 'working', action: 'Start' },
  working: { label: 'Working', className: 'text-violet-200 bg-violet-300/[0.12]', next: 'review', action: 'Review' },
  needs_you: { label: 'Needs you', className: 'text-amber-200 bg-amber-300/[0.11]' },
  review: { label: 'Review', className: 'text-signal-ice bg-signal-ice/[0.1]', next: 'done', action: 'Archive' },
  deferred: { label: 'Deferred', className: 'text-text-dim bg-white/[0.06]', next: 'clarifying', action: 'Resume' },
  todo: { label: 'Clarifying', className: 'text-amber-200 bg-amber-300/[0.11]', next: 'ready', action: 'Ready' },
  in_progress: { label: 'Working', className: 'text-violet-200 bg-violet-300/[0.12]', next: 'review', action: 'Review' },
  backlog: { label: 'Deferred', className: 'text-text-dim bg-white/[0.06]', next: 'clarifying', action: 'Resume' },
  blocked: { label: 'Needs you', className: 'text-amber-200 bg-amber-300/[0.11]' },
}

function Divider({ onPointerDown }: { onPointerDown: (event: React.PointerEvent<HTMLDivElement>) => void }) {
  return <div role="separator" aria-orientation="vertical" onPointerDown={onPointerDown} className="group relative z-30 w-px shrink-0 cursor-col-resize bg-white/[0.08] touch-none"><span className="absolute inset-y-0 -left-1.5 w-3 transition-colors group-hover:bg-signal-ice/20 group-active:bg-signal-ice/30" /></div>
}

function GlobalSidebar({ projectName }: { projectName: string }) {
  const row = (Icon: typeof Plus, label: string, active = false) => <button type="button" className={`flex h-6 w-full items-center gap-2 rounded-md px-2 text-left font-mono text-[9px] tracking-[-0.01em] transition-colors ${active ? 'bg-white/[0.08] text-white' : 'text-white/62 hover:bg-white/[0.055] hover:text-white'}`}><Icon size={11} strokeWidth={1.6} />{label}</button>
  return <aside className="flex h-full shrink-0 flex-col bg-[#171717] px-2 py-2.5"><div className="space-y-0.5">{row(Plus, 'New task')}{row(Bot, 'Agent', true)}{row(Search, 'Search')}{row(Sparkles, 'Apps')}{row(Gauge, 'Scheduled')}{row(Library, 'Library')}</div><div className="mt-4"><div className="mb-1 flex items-center justify-between px-1.5 font-mono text-[8px] uppercase tracking-[0.1em] text-white/35"><span>Projects</span><Plus size={10} /></div>{row(FolderGit2, projectName, true)}</div><div className="mt-4"><div className="mb-1 flex items-center justify-between px-1.5 font-mono text-[8px] uppercase tracking-[0.1em] text-white/35"><span>Tasks</span><ListTodo size={10} /></div>{row(CheckSquare2, 'Project work')}</div><div className="mt-auto border-t border-white/[0.06] pt-2">{row(Settings2, 'Settings')}</div></aside>
}

function TaskLane({ workspace, width, onTaskStatus }: { workspace?: WorkspaceSnapshot; width: number; onTaskStatus: (taskId: string, status: WorkspaceTaskStatus) => Promise<void> }) {
  const [expandedTask, setExpandedTask] = useState<string>()
  const activeTasks = workspace?.tasks.filter((task) => task.status !== 'done') || []
  const doneCount = workspace?.tasks.filter((task) => task.status === 'done').length || 0
  const moduleName = (moduleId: string) => workspace?.modules.find((module) => module.id === moduleId)?.title || 'Project'
  return <aside style={{ width }} className="flex h-full min-w-[168px] max-w-[340px] shrink-0 flex-col bg-[#181818]"><header className="flex h-8 shrink-0 items-center justify-between border-b border-white/[0.08] px-2.5"><span className="font-mono text-[8px] uppercase tracking-[0.12em] text-white/55">Task cards</span><span className="font-mono text-[8px] text-white/35">{activeTasks.length} · {doneCount}</span></header><div className="scrollbar-thin flex-1 space-y-2 overflow-y-auto p-2">{activeTasks.length ? activeTasks.map((task) => { const meta = TASK_META[task.status] || TASK_META.clarifying; const expanded = expandedTask === task.id; return <article key={task.id} className={`rounded-md border shadow-[0_2px_10px_rgba(0,0,0,.16)] ${expanded ? 'border-signal-ice/35 bg-signal-ice/[0.055]' : 'border-white/[0.09] bg-[#202020]'}`}><button type="button" onClick={() => setExpandedTask(expanded ? undefined : task.id)} className="w-full p-2.5 text-left"><div className="flex items-start gap-1.5"><span className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${meta.className.includes('amber') ? 'bg-amber-300' : meta.className.includes('violet') ? 'bg-violet-300' : 'bg-signal-ice'}`} /><p className="line-clamp-2 flex-1 text-[10px] leading-4 text-white/87">{task.title}</p><ChevronRight size={11} className={`mt-0.5 text-white/35 transition-transform ${expanded ? 'rotate-90' : ''}`} /></div><div className="mt-2.5 flex items-center justify-between gap-2"><span className={`rounded-sm px-1.5 py-0.5 font-mono text-[7px] uppercase tracking-[0.08em] ${meta.className}`}>{meta.label}</span><span className="max-w-[82px] truncate font-mono text-[7px] uppercase tracking-[0.06em] text-white/35">{moduleName(task.module_id)}</span></div></button>{expanded && <div className="border-t border-white/[0.07] px-2.5 pb-2.5 pt-2"><p className="text-[9px] leading-4 text-white/52">{task.description || 'Waiting for project context.'}</p>{meta.next && <button type="button" onClick={() => void onTaskStatus(task.id, meta.next!)} className="mt-2.5 w-full rounded-sm border border-signal-ice/25 bg-signal-ice/[0.08] py-1.5 font-mono text-[8px] uppercase tracking-[0.08em] text-signal-ice">{meta.action}</button>}</div>}</article> }) : <p className="rounded-md border border-dashed border-white/[0.1] p-2 text-[9px] leading-4 text-white/40">Project tasks and file markers appear here.</p>}</div></aside>
}

export default function App() {
  const [sidebarWidth, setSidebarWidth] = useState(() => Number(localStorage.getItem('agent-room-sidebar-width')) || 132)
  const [chatWidth, setChatWidth] = useState(() => Number(localStorage.getItem('agent-room-chat-width')) || 500)
  const [taskWidth, setTaskWidth] = useState(() => Number(localStorage.getItem('agent-room-task-width')) || 220)
  const [apiHealthy, setApiHealthy] = useState<boolean | null>(null)
  const auth = useAuth()
  const chat = useChat()
  const workspace = useWorkspace()
  const socket = useWebSocket(chat.appendEvent)
  const projectName = workspace.workspace?.project.name || workspace.repository?.repository_url?.split('/').pop()?.replace(/\.git$/, '') || 'New project'
  const captureTarget = workspace.selectedModule || workspace.workspace?.modules[0]
  const checkHealth = useCallback(async () => { try { const apiUrl = import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app'; const response = await fetch(`${apiUrl.replace(/\/$/, '')}/v1/healthz`); setApiHealthy(response.ok) } catch { setApiHealthy(false) } }, [])
  useEffect(() => { void checkHealth() }, [checkHealth])
  useEffect(() => { localStorage.setItem('agent-room-sidebar-width', String(sidebarWidth)); localStorage.setItem('agent-room-chat-width', String(chatWidth)); localStorage.setItem('agent-room-task-width', String(taskWidth)) }, [chatWidth, sidebarWidth, taskWidth])
  const startResize = (target: 'sidebar' | 'chat' | 'tasks') => (event: React.PointerEvent<HTMLDivElement>) => { event.preventDefault(); const startX = event.clientX; const startWidth = target === 'sidebar' ? sidebarWidth : target === 'chat' ? chatWidth : taskWidth; const limits = target === 'sidebar' ? [112, 260] : target === 'chat' ? [360, 820] : [168, 340]; const onMove = (move: PointerEvent) => { const next = clamp(startWidth + move.clientX - startX, limits[0], limits[1]); if (target === 'sidebar') setSidebarWidth(next); else if (target === 'chat') setChatWidth(next); else setTaskWidth(next) }; const onUp = () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp) }; window.addEventListener('pointermove', onMove); window.addEventListener('pointerup', onUp) }
  return <div className="h-screen min-h-[560px] overflow-hidden bg-[#1b1b1b] font-sans text-[#ececec] selection:bg-signal-ice/25"><header className="flex h-7 items-center justify-between border-b border-white/[0.055] bg-[#242424] px-2.5"><div className="flex items-center gap-2 font-mono text-[8px] text-white/42"><span className="text-white/66">Agent Room</span><span>·</span><span>{projectName}</span></div><div className="flex items-center gap-2 font-mono text-[8px] text-white/42"><span className={`h-1.5 w-1.5 rounded-full ${apiHealthy === false ? 'bg-rose-400' : 'bg-emerald-400'}`} /><span>{auth.status?.authenticated ? auth.status.user?.login || 'Connected' : 'Offline'}</span></div></header><main className="flex h-[calc(100vh-28px)] min-h-0"><div style={{ width: sidebarWidth }} className="min-w-[112px] max-w-[260px] shrink-0"><GlobalSidebar projectName={projectName} /></div><Divider onPointerDown={startResize('sidebar')} /><section style={{ width: chatWidth }} className="min-w-[360px] max-w-[820px] shrink-0 bg-[#1c1c1c]"><Chat messages={chat.messages} plan={chat.plan} events={chat.events} approvals={chat.approvals} loading={chat.loading} error={chat.error} stage={chat.stage} connected={socket.connected} runId={chat.runId} moduleTitle={workspace.selectedModule?.title} onSend={chat.sendMessage} onApprovalDecision={chat.decideApproval} onCaptureNote={async (runId, title, content) => { if (!captureTarget) throw new Error('Index the project before saving context.'); await workspace.createNote(captureTarget, title, content, runId) }} onCaptureTask={async (runId, title, description) => { if (!captureTarget) throw new Error('Index the project before creating a task.'); await workspace.createTask(captureTarget, title, description, runId) }} approvalMode={chat.approvalMode} onApprovalModeChange={chat.setApprovalMode} /></section><Divider onPointerDown={startResize('chat')} /><TaskLane width={taskWidth} workspace={workspace.workspace} onTaskStatus={workspace.updateTaskStatus} /><Divider onPointerDown={startResize('tasks')} /><section className="relative min-w-0 flex-1 bg-[#151515]"><TaskGraph plan={chat.plan} events={chat.events} connected={socket.connected} workspace={workspace.workspace} repository={workspace.repository} files={workspace.files} indexing={workspace.indexing} selectedModuleId={workspace.selectedModuleId} onSelectModule={workspace.setSelectedModuleId} onIndexRepository={() => void workspace.indexRepository()} /></section></main></div>
}
