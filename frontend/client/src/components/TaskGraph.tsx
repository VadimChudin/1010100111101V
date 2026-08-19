// The canvas is the durable module map; active run steps remain available as a fallback before workspace loads.
import { useEffect, useMemo } from 'react'
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, useEdgesState, useNodesState } from '@xyflow/react'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import { Check, CircleDashed, Loader2, Wrench } from 'lucide-react'
import type { AgentEvent, PlanStep, WorkspaceMarker, WorkspaceModule, WorkspaceSnapshot } from '../types'

function PlanNode({ data }: NodeProps) {
  const step = data.step as PlanStep
  const status = step.status || 'pending'
  const Icon = status === 'completed' ? Check : status === 'active' ? Loader2 : step.tool ? Wrench : CircleDashed
  return <div className={`graph-node graph-node-${status}`}><Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-signal-ice" /><div className="flex items-start gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-[9px] border border-white/10 bg-white/[0.06] text-signal-ice"><Icon size={13} className={status === 'active' ? 'animate-spin' : ''} /></span><div className="min-w-0"><div className="font-mono text-[9px] uppercase tracking-[0.16em] text-text-dim">{status === 'active' ? 'Executing' : status === 'completed' ? 'Complete' : step.tool || 'Queued'}</div><div className="mt-1 font-display text-[13px] font-medium leading-5 text-white">{step.title}</div>{step.description && <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-text-dim">{step.description}</div>}</div></div><Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-signal-ice" /></div>
}

function ModuleNode({ data }: NodeProps) {
  const module = data.module as WorkspaceModule
  const markers = data.markers as WorkspaceMarker[]
  const selected = Boolean(data.selected)
  const counts = markers.reduce<Record<string, number>>((accumulator, marker) => ({ ...accumulator, [marker.type]: (accumulator[marker.type] || 0) + 1 }), {})
  return <div className={`min-w-[215px] rounded-[16px] border p-4 shadow-xl transition-colors ${selected ? 'border-signal-ice/80 bg-signal-ice/[0.12]' : 'border-white/15 bg-[#101820]/95 hover:border-signal-ice/40'}`}><Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-signal-ice" /><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-mono text-[9px] uppercase tracking-[0.14em] text-signal-ice">{module.kind}</p><h3 className="mt-1 font-display text-[14px] font-semibold text-white">{module.title}</h3></div><span className="rounded border border-white/10 px-1.5 py-0.5 font-mono text-[8px] uppercase tracking-[0.1em] text-text-dim">{module.status}</span></div><p className="mt-2 truncate font-mono text-[9px] text-text-dim">{module.source_scope || 'No source scope'}</p>{Object.keys(counts).length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{Object.entries(counts).map(([type, count]) => <span key={type} className={`rounded-full px-2 py-0.5 font-mono text-[9px] ${type === 'error' || type === 'blocked' ? 'bg-alert/15 text-alert' : type === 'task' ? 'bg-signal-ice/15 text-signal-ice' : 'bg-white/[0.07] text-text-muted'}`}>{type} {count}</span>)}</div>}<Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-signal-ice" /></div>
}

const nodeTypes = { mission: PlanNode, module: ModuleNode }
const starterPlan: PlanStep[] = [
  { id: 'step-1', title: 'Queue a brief', description: 'Accept the operator request.', status: 'pending', tool: 'Input' },
  { id: 'step-2', title: 'Build a plan', description: 'Decompose the request into executable steps.', status: 'pending', tool: 'Planner' },
  { id: 'step-3', title: 'Run tools', description: 'Execute the selected operations and collect outputs.', status: 'pending', tool: 'Runtime' },
  { id: 'step-4', title: 'Review output', description: 'Validate the run before returning the answer.', status: 'pending', tool: 'Review' },
]

export default function TaskGraph({ plan, events, connected, workspace, selectedModuleId, onSelectModule }: { plan: PlanStep[]; events: AgentEvent[]; connected: boolean; workspace?: WorkspaceSnapshot; selectedModuleId?: string; onSelectModule?: (moduleId: string) => void }) {
  const usingWorkspace = Boolean(workspace?.modules.length)
  const safePlan = plan.length ? plan : starterPlan
  const moduleMarkers = useMemo(() => workspace?.markers.reduce<Record<string, WorkspaceMarker[]>>((groups, marker) => ({ ...groups, [marker.module_id]: [...(groups[marker.module_id] || []), marker] }), {}) || {}, [workspace])
  const desiredNodes = useMemo<Node[]>(() => usingWorkspace
    ? workspace!.modules.map((module) => ({ id: module.id, type: 'module', position: { x: module.position_x, y: module.position_y }, data: { module, markers: moduleMarkers[module.id] || [], selected: selectedModuleId === module.id } }))
    : safePlan.map((step, index) => ({ id: step.id, type: 'mission', position: { x: 100 + (index % 2) * 300, y: 90 + Math.floor(index / 2) * 180 }, data: { step } })),
  [moduleMarkers, safePlan, selectedModuleId, usingWorkspace, workspace])
  const desiredEdges = useMemo<Edge[]>(() => usingWorkspace
    ? workspace!.modules.flatMap((module, index) => (module.dependencies.length ? module.dependencies.filter((dependency) => workspace!.modules.some((candidate) => candidate.id === dependency)).map((dependency) => ({ id: `${dependency}-${module.id}`, source: dependency, target: module.id })) : index ? [{ id: `${workspace!.modules[index - 1].id}-${module.id}`, source: workspace!.modules[index - 1].id, target: module.id }] : [])).map((edge) => ({ ...edge, animated: false, style: { stroke: '#527487', strokeWidth: 1, opacity: 0.45 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#527487' } }))
    : safePlan.slice(1).map((step, index) => ({ id: `edge-${index}`, source: safePlan[index].id, target: step.id, animated: true, style: { stroke: '#9de8ff', strokeWidth: 1, opacity: 0.5 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#9de8ff' } })),
  [safePlan, usingWorkspace, workspace])
  const [nodes, setNodes, onNodesChange] = useNodesState(desiredNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(desiredEdges)

  useEffect(() => { setNodes(desiredNodes); setEdges(desiredEdges) }, [desiredEdges, desiredNodes, setEdges, setNodes])
  useEffect(() => {
    if (usingWorkspace) return
    const latestId = events[events.length - 1]?.step_id || events[events.length - 1]?.stepId
    if (!latestId) return
    setNodes((current) => current.map((node) => node.id === latestId ? { ...node, data: { ...node.data, step: { ...(node.data.step as PlanStep), status: 'active' } } } : node))
  }, [events, setNodes, usingWorkspace])

  const selected = workspace?.modules.find((module) => module.id === selectedModuleId)
  return <section className="relative min-h-[620px] flex-1 overflow-hidden bg-[#0a0e13]" aria-label="Project workspace graph"><div className="absolute left-5 top-5 z-10 sm:left-8 sm:top-7"><p className="eyebrow">{usingWorkspace ? 'Project workspace' : 'Execution topology'}</p><h2 className="mt-1 font-display text-xl font-semibold tracking-[-0.03em] text-white">{usingWorkspace ? workspace!.project.name : 'Task graph'}</h2><p className="mt-1 max-w-[280px] text-xs leading-5 text-text-dim">{usingWorkspace ? selected ? `${selected.title} is in focus.` : 'Select a module to inspect its durable context.' : 'A live map of the agent plan and the work moving through it.'}</p></div><div className="absolute right-5 top-5 z-10 flex items-center gap-2 rounded-full border border-white/10 bg-[#101820]/80 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-dim backdrop-blur sm:right-8 sm:top-7"><span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-complete live-dot' : 'bg-alert'}`} />{connected ? 'Stream synced' : 'Stream offline'}</div><div className="absolute bottom-5 left-5 z-10 max-w-[250px] font-mono text-[10px] uppercase tracking-[0.1em] text-text-dim sm:bottom-7 sm:left-8">{usingWorkspace ? `${workspace!.modules.length} modules · ${workspace!.markers.length} markers` : plan.length ? `${plan.length} steps in current plan` : 'No active plan'}</div><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodeClick={(_, node) => usingWorkspace && onSelectModule?.(node.id)} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.35 }} minZoom={0.45} maxZoom={1.35} proOptions={{ hideAttribution: true }}><Background color="#29343e" gap={28} size={1} /><Controls showInteractive={false} /><MiniMap nodeColor={(node) => node.type === 'module' ? '#527487' : ((node.data as { step?: PlanStep })?.step?.status === 'active' ? '#9de8ff' : '#344653')} maskColor="rgba(6, 10, 14, 0.76)" /></ReactFlow></section>
}
