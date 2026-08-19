// Dark Mission Control: the graph is a spatial trace of the same run shown in the chat rail.
import { useEffect, useMemo } from 'react'
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow, useEdgesState, useNodesState } from '@xyflow/react'
import type { Edge, Node, NodeProps } from '@xyflow/react'
import { Check, CircleDashed, Loader2, Wrench } from 'lucide-react'
import type { AgentEvent, PlanStep } from '../types'

function GraphNode({ data }: NodeProps) {
  const step = data.step as PlanStep
  const status = step.status || 'pending'
  const Icon = status === 'completed' ? Check : status === 'active' ? Loader2 : step.tool ? Wrench : CircleDashed
  return <div className={`graph-node graph-node-${status}`}><Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-signal-ice" /><div className="flex items-start gap-3"><span className="grid h-7 w-7 shrink-0 place-items-center rounded-[9px] border border-white/10 bg-white/[0.06] text-signal-ice"> <Icon size={13} className={status === 'active' ? 'animate-spin' : ''} /></span><div className="min-w-0"><div className="font-mono text-[9px] uppercase tracking-[0.16em] text-text-dim">{status === 'active' ? 'Executing' : status === 'completed' ? 'Complete' : step.tool || 'Queued'}</div><div className="mt-1 font-display text-[13px] font-medium leading-5 text-white">{step.title}</div>{step.description && <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-text-dim">{step.description}</div>}</div></div><Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-signal-ice" /></div>
}

const nodeTypes = { mission: GraphNode }

const starterPlan: PlanStep[] = [
  { id: 'step-1', title: 'Queue a brief', description: 'Accept the operator request.', status: 'pending', tool: 'Input' },
  { id: 'step-2', title: 'Build a plan', description: 'Decompose the request into executable steps.', status: 'pending', tool: 'Planner' },
  { id: 'step-3', title: 'Run tools', description: 'Execute the selected operations and collect outputs.', status: 'pending', tool: 'Runtime' },
  { id: 'step-4', title: 'Review output', description: 'Validate the run before returning the answer.', status: 'pending', tool: 'Review' },
]

export default function TaskGraph({ plan, events, connected }: { plan: PlanStep[]; events: AgentEvent[]; connected: boolean }) {
  const safePlan = plan.length ? plan : starterPlan
  const initialNodes = useMemo<Node[]>(() => safePlan.map((step, index) => ({ id: step.id, type: 'mission', position: { x: 100 + (index % 2) * 300, y: 90 + Math.floor(index / 2) * 180 }, data: { step } })), [])
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const initialEdges = useMemo<Edge[]>(() => safePlan.slice(1).map((step, index) => ({ id: `edge-${index}`, source: safePlan[index].id, target: step.id, animated: true, style: { stroke: '#9de8ff', strokeWidth: 1, opacity: 0.5 }, markerEnd: { type: MarkerType.ArrowClosed, color: '#9de8ff' } })), [])
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    const latest = events[events.length - 1]
    const latestId = latest?.step_id || latest?.stepId
    const updated = safePlan.map((step, index) => ({ id: step.id, type: 'mission', position: { x: 100 + (index % 2) * 300, y: 90 + Math.floor(index / 2) * 180 }, data: { step: latestId === step.id && step.status === 'pending' ? { ...step, status: 'active' } : step } }))
    setNodes(updated)
  }, [events, safePlan, setNodes])

  return <section className="relative min-h-[620px] flex-1 overflow-hidden bg-[#0a0e13]" aria-label="Agent task graph"><div className="absolute left-5 top-5 z-10 sm:left-8 sm:top-7"><p className="eyebrow">Execution topology</p><h2 className="mt-1 font-display text-xl font-semibold tracking-[-0.03em] text-white">Task graph</h2><p className="mt-1 max-w-[260px] text-xs leading-5 text-text-dim">A live map of the agent's plan and the work moving through it.</p></div><div className="absolute right-5 top-5 z-10 flex items-center gap-2 rounded-full border border-white/10 bg-[#101820]/80 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.12em] text-text-dim backdrop-blur sm:right-8 sm:top-7"><span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-complete live-dot' : 'bg-alert'}`} />{connected ? 'Stream synced' : 'Stream offline'}</div><div className="absolute bottom-5 left-5 z-10 max-w-[220px] font-mono text-[10px] uppercase tracking-[0.1em] text-text-dim sm:bottom-7 sm:left-8">{plan.length ? `${plan.length} steps in current plan` : 'No active plan'}</div><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.35 }} minZoom={0.45} maxZoom={1.35} proOptions={{ hideAttribution: true }}><Background color="#29343e" gap={28} size={1} /><Controls showInteractive={false} /><MiniMap nodeColor={(node) => { const step = (node.data as { step?: PlanStep })?.step; return step?.status === 'active' ? '#9de8ff' : step?.status === 'completed' ? '#7de2b3' : '#344653' }} maskColor="rgba(6, 10, 14, 0.76)" /></ReactFlow></section>
}
