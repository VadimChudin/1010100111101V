import { useEffect, useMemo, useState } from 'react'
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, useEdgesState, useNodesState } from '@xyflow/react'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import { ChevronRight, CircleDashed, FileCode2, Files, FolderTree, GitBranch, GitPullRequest, Loader2, Network, RefreshCw, StickyNote, Wrench, X } from 'lucide-react'
import type { AgentEvent, PlanStep, RepositoryFile, RepositoryIndex, WorkspaceMarker, WorkspaceModule, WorkspaceSnapshot } from '../types'

type MapLens = 'modules' | 'files' | 'dependencies' | 'changes' | 'tasks'

const LENSES: Array<{ id: MapLens; label: string; icon: typeof Files }> = [
  { id: 'modules', label: 'Modules', icon: FolderTree },
  { id: 'files', label: 'Files', icon: Files },
  { id: 'dependencies', label: 'Dependencies', icon: Network },
  { id: 'changes', label: 'Git changes', icon: GitPullRequest },
  { id: 'tasks', label: 'Tasks', icon: StickyNote },
]

function PlanNode({ data }: NodeProps) {
  const step = data.step as PlanStep
  const status = step.status || 'pending'
  const Icon = status === 'active' ? Loader2 : step.tool ? Wrench : CircleDashed
  return <div className={`graph-node graph-node-${status}`}><Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-signal-ice" /><div className="flex items-start gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-[9px] border border-white/10 bg-white/[0.06] text-signal-ice"><Icon size={13} className={status === 'active' ? 'animate-spin' : ''} /></span><div className="min-w-0"><div className="font-mono text-[9px] uppercase tracking-[0.16em] text-text-dim">{status === 'active' ? 'Clarifying' : step.tool || 'Project task'}</div><div className="mt-1 font-display text-[13px] font-medium leading-5 text-white">{step.title}</div>{step.description && <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-text-dim">{step.description}</div>}</div></div><Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-signal-ice" /></div>
}

function ModuleNode({ data }: NodeProps) {
  const module = data.module as WorkspaceModule
  const markers = data.markers as WorkspaceMarker[]
  const selected = Boolean(data.selected)
  const taskCount = markers.filter((marker) => marker.type === 'task').length
  const noteCount = markers.filter((marker) => marker.type === 'note' || marker.type === 'decision').length
  return <div title={module.source_scope} className={`min-w-[218px] rounded-[15px] border p-4 shadow-xl transition-all ${selected ? 'border-signal-ice/80 bg-signal-ice/[0.11] shadow-[0_0_0_4px_rgba(159,232,255,.07)]' : 'border-white/12 bg-[#171a20]/95 hover:border-signal-ice/42 hover:-translate-y-0.5'}`}><Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-signal-ice" /><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-mono text-[8px] uppercase tracking-[0.14em] text-signal-ice">{module.kind} · {module.origin}</p><h3 className="mt-1 truncate font-display text-[13px] font-semibold text-white">{module.title}</h3></div><span className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-[0.1em] text-text-dim">{module.status}</span></div><p className="mt-2 truncate font-mono text-[9px] text-text-dim">{module.source_scope || 'No source scope'}</p>{(taskCount > 0 || noteCount > 0) && <div className="mt-3 flex gap-1.5">{taskCount > 0 && <span className="rounded-full bg-signal-ice/[0.13] px-2 py-0.5 font-mono text-[8px] text-signal-ice">Task {taskCount}</span>}{noteCount > 0 && <span className="rounded-full bg-white/[0.07] px-2 py-0.5 font-mono text-[8px] text-text-muted">Context {noteCount}</span>}</div>}<Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-signal-ice" /></div>
}

function FileNode({ data }: NodeProps) {
  const file = data.file as RepositoryFile
  const selected = Boolean(data.selected)
  const markerCount = Number(data.markerCount || 0)
  const connected = Boolean(data.connected)
  return <div title={file.path} className={`w-[150px] rounded-md border px-2 py-1.5 transition-all ${selected ? 'border-signal-ice/80 bg-signal-ice/[0.12] shadow-[0_0_0_3px_rgba(159,232,255,.07)]' : connected ? 'border-signal-ice/22 bg-[#171a20]/95 hover:border-signal-ice/50' : 'border-white/[0.09] bg-[#171a20]/88 hover:border-white/25'}`}><Handle type="target" position={Position.Left} className="!h-1.5 !w-1.5 !border-0 !bg-signal-ice" /><div className="flex items-start gap-1.5"><FileCode2 size={11} className="mt-0.5 shrink-0 text-signal-ice/85" /><div className="min-w-0"><p className="truncate font-mono text-[8px] text-white/90">{file.path.split('/').at(-1)}</p><p className="mt-0.5 truncate font-mono text-[6px] uppercase tracking-[0.09em] text-text-dim">{file.language || 'file'} · {file.size ? `${Math.max(1, Math.round(file.size / 1024))} kb` : 'size ?'}</p></div>{markerCount > 0 && <span className="ml-auto rounded bg-amber-300/15 px-1 py-0.5 font-mono text-[7px] text-amber-200">{markerCount}</span>}</div><Handle type="source" position={Position.Right} className="!h-1.5 !w-1.5 !border-0 !bg-signal-ice" /></div>
}

function fileSpiderPositions(files: RepositoryFile[], edges: Array<{ source_path: string; target_path: string }>) {
  const paths = files.map((file) => file.path)
  const adjacency = new Map(paths.map((path) => [path, new Set<string>()]))
  for (const edge of edges) {
    adjacency.get(edge.source_path)?.add(edge.target_path)
    adjacency.get(edge.target_path)?.add(edge.source_path)
  }
  const visited = new Set<string>()
  const components: string[][] = []
  const isolated: string[] = []
  for (const path of paths) {
    if (visited.has(path)) continue
    const queue = [path]
    const component: string[] = []
    visited.add(path)
    while (queue.length) {
      const current = queue.shift()!
      component.push(current)
      for (const next of Array.from(adjacency.get(current) || [])) if (!visited.has(next)) { visited.add(next); queue.push(next) }
    }
    if (component.length > 1) components.push(component)
    else isolated.push(path)
  }
  components.sort((a, b) => b.length - a.length || a[0].localeCompare(b[0]))
  const positions = new Map<string, { x: number; y: number }>()
  components.forEach((component, index) => {
    const angle = index * 2.399963229728653
    const distance = index === 0 ? 0 : 760 + Math.floor(index / 5) * 360
    const center = { x: 900 + Math.cos(angle) * distance, y: 620 + Math.sin(angle) * distance }
    const ranked = [...component].sort((a, b) => (adjacency.get(b)?.size || 0) - (adjacency.get(a)?.size || 0) || a.localeCompare(b))
    positions.set(ranked[0], center)
    ranked.slice(1).forEach((path, nodeIndex) => {
      const ring = Math.floor(Math.sqrt(nodeIndex))
      const radius = 250 + ring * 130
      const nodeAngle = (nodeIndex / Math.max(1, ranked.length - 1)) * Math.PI * 2 + angle / 3
      positions.set(path, { x: center.x + Math.cos(nodeAngle) * radius, y: center.y + Math.sin(nodeAngle) * radius })
    })
  })
  const isolatedColumns = Math.max(6, Math.ceil(Math.sqrt(Math.max(1, isolated.length))))
  const isolatedTop = components.length ? 1560 + Math.ceil(components.length / 5) * 340 : 160
  isolated.forEach((path, index) => positions.set(path, { x: 100 + (index % isolatedColumns) * 172, y: isolatedTop + Math.floor(index / isolatedColumns) * 72 }))
  return positions
}

const nodeTypes = { mission: PlanNode, module: ModuleNode, file: FileNode }
const starterPlan: PlanStep[] = [
  { id: 'step-1', title: 'Describe the work', description: 'Share the outcome you want from the project.', status: 'pending', tool: 'Conversation' },
  { id: 'step-2', title: 'Clarify the scope', description: 'Agent Room will collect only the context needed to begin safely.', status: 'pending', tool: 'Context' },
]

function ProjectInspector({ module, workspace, files, onClose }: { module?: WorkspaceModule; workspace?: WorkspaceSnapshot; files: RepositoryFile[]; onClose: () => void }) {
  const moduleFiles = useMemo(() => module ? files.filter((file) => file.kind === 'file' && file.path.startsWith(module.source_scope)).slice(0, 8) : [], [files, module])
  const notes = useMemo(() => module ? workspace?.notes.filter((note) => note.module_id === module.id).slice(0, 3) || [] : [], [module, workspace?.notes])
  const tasks = useMemo(() => module ? workspace?.tasks.filter((task) => task.module_id === module.id).slice(0, 4) || [] : [], [module, workspace?.tasks])
  if (!module) return null
  return <aside className="absolute bottom-4 right-4 top-4 z-20 hidden w-[314px] overflow-hidden rounded-2xl border border-white/10 bg-[#15181e]/96 shadow-2xl backdrop-blur-xl xl:flex xl:flex-col"><div className="flex items-start justify-between border-b border-white/[0.08] px-5 py-4"><div className="min-w-0"><p className="font-mono text-[9px] uppercase tracking-[0.14em] text-signal-ice">Module inspector</p><h2 className="mt-1 truncate text-base font-semibold tracking-[-0.03em] text-white">{module.title}</h2><p className="mt-1 truncate font-mono text-[9px] text-text-dim">{module.source_scope}</p></div><button type="button" onClick={onClose} className="grid h-7 w-7 place-items-center rounded-lg text-text-dim transition-colors hover:bg-white/[0.07] hover:text-white" aria-label="Close inspector"><X size={15} /></button></div><div className="scrollbar-thin flex-1 overflow-y-auto px-5 py-5"><section><p className="font-mono text-[9px] uppercase tracking-[0.13em] text-text-dim">Dependencies</p><div className="mt-3 flex flex-wrap gap-1.5">{module.dependencies.length ? module.dependencies.map((dependency) => <span key={dependency} className="max-w-full truncate rounded-full border border-signal-ice/15 bg-signal-ice/[0.06] px-2 py-1 font-mono text-[8px] text-signal-ice">{dependency}</span>) : <span className="text-xs text-text-dim">No module links recorded yet.</span>}</div></section><section className="mt-6 border-t border-white/[0.08] pt-5"><p className="font-mono text-[9px] uppercase tracking-[0.13em] text-text-dim">Tracked files · {moduleFiles.length}</p><div className="mt-3 space-y-1.5">{moduleFiles.length ? moduleFiles.map((file) => <div key={file.path} className="group flex items-center gap-2 rounded-lg border border-white/[0.07] bg-white/[0.025] px-2.5 py-2"><FileCode2 size={12} className="shrink-0 text-signal-ice/80" /><span className="min-w-0 flex-1 truncate font-mono text-[9px] text-white/80">{file.path}</span><ChevronRight size={12} className="text-text-dim transition-transform group-hover:translate-x-0.5" /></div>) : <p className="text-xs leading-5 text-text-dim">Index this source scope to reveal its tracked files.</p>}</div></section><section className="mt-6 border-t border-white/[0.08] pt-5"><p className="font-mono text-[9px] uppercase tracking-[0.13em] text-text-dim">Attached work · {tasks.length}</p><div className="mt-3 space-y-2">{tasks.length ? tasks.map((task) => <article key={task.id} className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3"><p className="text-xs font-medium leading-5 text-white/90">{task.title}</p><p className="mt-1 font-mono text-[8px] uppercase tracking-[0.1em] text-amber-200">{task.status.replace('_', ' ')}</p></article>) : <p className="text-xs leading-5 text-text-dim">No task marker is attached to this module.</p>}</div></section><section className="mt-6 border-t border-white/[0.08] pt-5"><p className="font-mono text-[9px] uppercase tracking-[0.13em] text-text-dim">Context notes · {notes.length}</p><div className="mt-3 space-y-2">{notes.map((note) => <article key={note.id} className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3"><p className="text-xs font-medium text-white/85">{note.title}</p><p className="mt-1 line-clamp-3 text-[11px] leading-5 text-text-muted">{note.content}</p></article>)}</div></section></div></aside>
}

function FileInspector({ file, onClose }: { file?: RepositoryFile; onClose: () => void }) {
  if (!file) return null
  const folder = file.path.includes('/') ? file.path.split('/').slice(0, -1).join('/') || '/' : '/'
  return <aside className="absolute bottom-4 right-4 top-4 z-20 hidden w-[272px] overflow-hidden rounded-xl border border-white/10 bg-[#15181e]/96 shadow-2xl backdrop-blur-xl xl:flex xl:flex-col"><div className="flex items-start justify-between border-b border-white/[0.08] px-4 py-3"><div className="min-w-0"><p className="font-mono text-[8px] uppercase tracking-[0.12em] text-signal-ice">File inspector</p><h2 className="mt-1 truncate text-[12px] font-medium text-white">{file.path.split('/').at(-1)}</h2><p className="mt-1 truncate font-mono text-[8px] text-text-dim">{folder}</p></div><button type="button" onClick={onClose} className="grid h-6 w-6 place-items-center rounded text-text-dim hover:bg-white/[0.07] hover:text-white" aria-label="Close file inspector"><X size={13} /></button></div><div className="space-y-4 p-4"><div className="grid grid-cols-2 gap-2"><div className="border border-white/[0.08] bg-white/[0.025] p-2"><p className="font-mono text-[7px] uppercase tracking-[0.1em] text-white/35">Language</p><p className="mt-1 font-mono text-[9px] text-white/75">{file.language || 'unknown'}</p></div><div className="border border-white/[0.08] bg-white/[0.025] p-2"><p className="font-mono text-[7px] uppercase tracking-[0.1em] text-white/35">Size</p><p className="mt-1 font-mono text-[9px] text-white/75">{file.size ? `${Math.max(1, Math.round(file.size / 1024))} kb` : 'unknown'}</p></div></div><section className="border-t border-white/[0.08] pt-3"><p className="font-mono text-[8px] uppercase tracking-[0.11em] text-white/35">Local source</p><p className="mt-2 text-[10px] leading-4 text-white/55">The file remains on the paired computer. Ask Agent Room to inspect a range or attach a task marker without copying the project to cloud.</p></section></div></aside>
}

export default function TaskGraph({ plan, events, connected, workspace, repository, files, indexing = false, selectedModuleId, onSelectModule, onIndexRepository }: { plan: PlanStep[]; events: AgentEvent[]; connected: boolean; workspace?: WorkspaceSnapshot; repository?: RepositoryIndex; files: RepositoryFile[]; indexing?: boolean; selectedModuleId?: string; onSelectModule?: (moduleId: string) => void; onIndexRepository?: () => void }) {
  // The dashboard opens on the concrete project surface: every indexed file,
  // not a simplified module summary or a task placeholder.
  const [lens, setLens] = useState<MapLens>('files')
  const [inspectorOpen, setInspectorOpen] = useState(true)
  const [selectedFilePath, setSelectedFilePath] = useState<string>()
  const usingWorkspace = Boolean(workspace?.modules.length)
  const safePlan = plan.length ? plan : starterPlan
  const selected = workspace?.modules.find((module) => module.id === selectedModuleId)
  const selectedFile = files.find((file) => file.path === selectedFilePath)
  const moduleMarkers = useMemo(() => workspace?.markers.reduce<Record<string, WorkspaceMarker[]>>((groups, marker) => ({ ...groups, [marker.module_id]: [...(groups[marker.module_id] || []), marker] }), {}) || {}, [workspace])
  const visibleFiles = useMemo(() => files.filter((file) => file.kind === 'file').filter((file) => lens !== 'changes' || Boolean(selected?.source_scope && file.path.startsWith(selected.source_scope))), [files, lens, selected?.source_scope])
  const markerByScope = useMemo(() => Object.fromEntries((workspace?.modules || []).map((module) => [module.source_scope, (moduleMarkers[module.id] || []).length])), [moduleMarkers, workspace?.modules])
  const visiblePathSet = useMemo(() => new Set(visibleFiles.map((file) => file.path)), [visibleFiles])
  const visibleFileDependencies = useMemo(() => (repository?.file_dependencies || []).filter((edge) => visiblePathSet.has(edge.source_path) && visiblePathSet.has(edge.target_path)), [repository?.file_dependencies, visiblePathSet])
  const filePositions = useMemo(() => fileSpiderPositions(visibleFiles, visibleFileDependencies), [visibleFileDependencies, visibleFiles])
  const selectedFileNeighbors = useMemo(() => new Set(visibleFileDependencies.flatMap((edge) => edge.source_path === selectedFilePath ? [edge.target_path] : edge.target_path === selectedFilePath ? [edge.source_path] : [])), [selectedFilePath, visibleFileDependencies])

  const desiredNodes = useMemo<Node[]>(() => {
    if (!usingWorkspace && visibleFiles.length === 0) return safePlan.map((step, index) => ({ id: step.id, type: 'mission', position: { x: 110 + (index % 2) * 310, y: 120 + Math.floor(index / 2) * 180 }, data: { step } }))
    if (lens === 'files' || lens === 'changes') {
      return visibleFiles.map((file) => ({ id: `file:${file.path}`, type: 'file', position: filePositions.get(file.path) || { x: 80, y: 80 }, data: { file, selected: selectedFilePath === file.path || (selected?.source_scope ? file.path.startsWith(selected.source_scope) : false), connected: selectedFileNeighbors.has(file.path) || visibleFileDependencies.some((edge) => edge.source_path === file.path || edge.target_path === file.path), markerCount: Object.entries(markerByScope).find(([scope]) => scope && file.path.startsWith(scope))?.[1] || 0 } }))
    }
    return workspace!.modules.map((module) => ({ id: module.id, type: 'module', position: { x: module.position_x, y: module.position_y }, data: { module, markers: moduleMarkers[module.id] || [], selected: selectedModuleId === module.id } }))
  }, [filePositions, lens, markerByScope, moduleMarkers, safePlan, selected?.source_scope, selectedFileNeighbors, selectedFilePath, selectedModuleId, usingWorkspace, visibleFileDependencies, visibleFiles, workspace])

  const desiredEdges = useMemo<Edge[]>(() => {
    if (!usingWorkspace && visibleFiles.length === 0) return safePlan.slice(1).map((step, index) => ({ id: `edge-${index}`, source: safePlan[index].id, target: step.id, animated: true, style: { stroke: '#9fe8ff', strokeWidth: 1, opacity: 0.48 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#9fe8ff' } }))
    if (lens === 'files' || lens === 'changes') return visibleFileDependencies.map((edge) => {
      const focused = Boolean(selectedFilePath) && (edge.source_path === selectedFilePath || edge.target_path === selectedFilePath)
      return { id: `file-edge:${edge.source_path}:${edge.target_path}`, source: `file:${edge.source_path}`, target: `file:${edge.target_path}`, animated: focused, style: { stroke: focused ? '#9fe8ff' : '#5b7f8e', strokeWidth: focused ? 1.7 : 0.8, opacity: selectedFilePath && !focused ? 0.08 : focused ? 0.92 : 0.42 }, markerEnd: { type: MarkerType.ArrowClosed, color: focused ? '#9fe8ff' : '#5b7f8e' } }
    })
    const base = workspace!.modules.flatMap((module, index) => module.dependencies.length ? module.dependencies.filter((dependency) => workspace!.modules.some((candidate) => candidate.id === dependency)).map((dependency) => ({ id: `${dependency}-${module.id}`, source: dependency, target: module.id })) : index ? [{ id: `${workspace!.modules[index - 1].id}-${module.id}`, source: workspace!.modules[index - 1].id, target: module.id }] : [])
    return base.map((edge) => { const focused = Boolean(selectedModuleId) && (edge.source === selectedModuleId || edge.target === selectedModuleId); return { ...edge, animated: focused, style: { stroke: focused ? '#9fe8ff' : '#52606d', strokeWidth: focused ? 1.8 : 1, opacity: selectedModuleId && !focused ? 0.12 : focused ? 0.9 : 0.43 }, markerEnd: { type: MarkerType.ArrowClosed, color: focused ? '#9fe8ff' : '#52606d' } } })
  }, [lens, safePlan, selectedFilePath, selectedModuleId, usingWorkspace, visibleFileDependencies, visibleFiles.length, workspace])

  const [nodes, setNodes, onNodesChange] = useNodesState(desiredNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(desiredEdges)
  useEffect(() => { setNodes(desiredNodes); setEdges(desiredEdges) }, [desiredEdges, desiredNodes, setEdges, setNodes])
  useEffect(() => { if (!usingWorkspace) { const latestId = events.at(-1)?.step_id || events.at(-1)?.stepId; if (latestId) setNodes((current) => current.map((node) => node.id === latestId ? { ...node, data: { ...node.data, step: { ...(node.data.step as PlanStep), status: 'active' } } } : node)) } }, [events, setNodes, usingWorkspace])

  const mapTitle = lens === 'files' ? 'File dependency spider' : lens === 'changes' ? 'Git changes lens' : lens === 'tasks' ? 'Tasks on the map' : lens === 'dependencies' ? 'Dependency map' : workspace?.project.name || 'Project map'
  return <section className="relative h-full min-h-[620px] flex-1 overflow-hidden bg-[#0d0f13]" aria-label="Project workspace map"><div className="absolute left-5 top-5 z-10 max-w-[calc(100%-40px)] sm:left-8 sm:top-7"><p className="eyebrow">Project canvas</p><h2 className="mt-1 text-xl font-semibold tracking-[-0.035em] text-white">{mapTitle}</h2><p className="mt-1 max-w-[460px] text-xs leading-5 text-text-dim">{usingWorkspace ? selectedFile ? `${selectedFile.path} is in focus. Its direct imports are highlighted.` : visibleFileDependencies.length ? `${visibleFileDependencies.length} real file imports are shown. Select a file to isolate its threads.` : 'Refresh the project index to extract real file imports; no synthetic links are drawn.' : 'Describe a project task in Chat to create a shared work context.'}</p><div className="scrollbar-thin mt-4 flex max-w-[calc(100vw-110px)] gap-1.5 overflow-x-auto pb-1">{LENSES.map(({ id, label, icon: Icon }) => <button type="button" key={id} onClick={() => setLens(id)} className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors ${lens === id ? 'border-signal-ice/35 bg-signal-ice/[0.1] text-signal-ice' : 'border-white/[0.1] bg-[#14171c]/82 text-text-dim hover:text-white'}`}><Icon size={11} />{label}</button>)}</div></div><div className="absolute right-5 top-5 z-10 flex items-center gap-2 sm:right-8 sm:top-7"><span className={`hidden items-center gap-1.5 rounded-full border border-white/10 bg-[#14171c]/82 px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim backdrop-blur sm:flex`}><span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-300 live-dot' : 'bg-rose-300'}`} />{connected ? 'Synced' : 'Offline'}</span><button type="button" onClick={onIndexRepository} disabled={indexing || !onIndexRepository} className="inline-flex items-center gap-1.5 rounded-full border border-signal-ice/30 bg-signal-ice/[0.07] px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-signal-ice transition-colors hover:bg-signal-ice/[0.14] disabled:opacity-60"><RefreshCw size={11} className={indexing ? 'animate-spin' : ''} />{indexing ? 'Indexing' : 'Refresh'}</button></div><div className="absolute bottom-5 left-5 z-10 rounded-full border border-white/[0.09] bg-[#14171c]/80 px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-text-dim sm:bottom-7 sm:left-8">{usingWorkspace ? `${workspace!.modules.length} modules · ${repository?.files_count ?? files.length} tracked` : 'No project index yet'}</div><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodeClick={(_, node) => { if (node.type === 'module') { setSelectedFilePath(undefined); onSelectModule?.(node.id); setInspectorOpen(true) } if (node.type === 'file') { const file = node.data.file as RepositoryFile; setSelectedFilePath(file.path); setInspectorOpen(true) } }} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.28 }} minZoom={0.32} maxZoom={1.4} proOptions={{ hideAttribution: true }}><Background color="#2b3037" gap={30} size={1} /><Controls showInteractive={false} /><MiniMap nodeColor={(node) => node.type === 'file' ? '#65717d' : node.type === 'module' ? '#5f8798' : '#47515d'} maskColor="rgba(11,13,16,.78)" /></ReactFlow>{inspectorOpen && (selectedFile ? <FileInspector file={selectedFile} onClose={() => setInspectorOpen(false)} /> : <ProjectInspector module={selected} workspace={workspace} files={files} onClose={() => setInspectorOpen(false)} />)}</section>
}
