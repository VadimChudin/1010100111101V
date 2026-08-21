import { useCallback, useEffect, useState } from 'react'
import { Bot, CheckCircle2, CircleAlert, Database, RefreshCw, Wrench } from 'lucide-react'

type LocalService = { state: string; detail: string }
type RuntimeStatus = {
  paired: boolean
  runtime: LocalService
  serena: LocalService
  graphiti: LocalService
  lastRepairAt: string | null
}
type AgentStatus = {
  configured: boolean
  provider: string
  preferred_chat_model: string
  fallback_models: number
}
type DesktopBridge = {
  runtimeStatus: () => Promise<RuntimeStatus>
  repairRuntime: (component: 'all' | 'serena' | 'graphiti' | 'runtime') => Promise<{ status: RuntimeStatus }>
}

const apiUrl = (import.meta.env.VITE_API_URL || 'https://app-production-cc16.up.railway.app').replace(/\/$/, '')
const desktopBridge = () => (window as Window & { agentRoom?: DesktopBridge }).agentRoom

function StatusDot({ state }: { state: string }) {
  const ready = state === 'ready'
  const attention = state === 'stopped' || state === 'installed'
  return <span className={`mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full ${ready ? 'bg-emerald-400' : attention ? 'bg-amber-300' : 'bg-rose-400'}`} />
}

function ServiceCard({ icon: Icon, title, service, actionLabel, onAction, working }: {
  icon: typeof Bot
  title: string
  service?: LocalService
  actionLabel?: string
  onAction?: () => void
  working: boolean
}) {
  return <article className="rounded-md border border-white/[0.09] bg-[#1d1d1d] p-3 shadow-[0_2px_10px_rgba(0,0,0,.14)]">
    <div className="flex items-start gap-2"><Icon size={14} strokeWidth={1.55} className="mt-0.5 text-signal-ice" /><div className="min-w-0 flex-1"><div className="flex items-center justify-between gap-2"><p className="font-mono text-[9px] uppercase tracking-[0.1em] text-white/74">{title}</p>{service && <div className="flex items-center gap-1.5"><StatusDot state={service.state} /><span className="font-mono text-[8px] uppercase tracking-[0.07em] text-white/43">{service.state.replace('_', ' ')}</span></div>}</div><p className="mt-1.5 text-[10px] leading-4 text-white/48">{service?.detail || 'Available in the Agent Room desktop application.'}</p></div></div>
    {onAction && actionLabel && <button type="button" onClick={onAction} disabled={working} className="mt-3 inline-flex items-center gap-1.5 rounded-sm border border-signal-ice/25 bg-signal-ice/[0.08] px-2 py-1.5 font-mono text-[8px] uppercase tracking-[0.08em] text-signal-ice transition-colors hover:bg-signal-ice/[0.15] disabled:cursor-wait disabled:opacity-45"><Wrench size={10} />{working ? 'Working…' : actionLabel}</button>}
  </article>
}

export default function RuntimeSettings() {
  const [runtime, setRuntime] = useState<RuntimeStatus>()
  const [agent, setAgent] = useState<AgentStatus>()
  const [notice, setNotice] = useState<string>()
  const [working, setWorking] = useState<string>()

  const refresh = useCallback(async () => {
    setNotice(undefined)
    const bridge = desktopBridge()
    const [runtimeResult, agentResult] = await Promise.allSettled([
      bridge?.runtimeStatus(),
      fetch(`${apiUrl}/v1/agent/status`, { credentials: 'include' }).then(async (response) => {
        if (response.status === 401) throw new Error('Session expired. Reconnect GitHub from the desktop setup screen.')
        if (!response.ok) throw new Error('Could not read the Agent connection status.')
        return response.json() as Promise<AgentStatus>
      }),
    ])
    if (runtimeResult.status === 'fulfilled') setRuntime(runtimeResult.value)
    if (agentResult.status === 'fulfilled') setAgent(agentResult.value)
    const errors = [runtimeResult, agentResult].filter((result): result is PromiseRejectedResult => result.status === 'rejected').map((result) => result.reason instanceof Error ? result.reason.message : 'Status refresh failed.')
    if (errors.length) setNotice(errors[0])
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const repair = useCallback(async (component: 'all' | 'serena' | 'graphiti' | 'runtime') => {
    const bridge = desktopBridge()
    if (!bridge) {
      setNotice('Local runtime controls are available in the Agent Room desktop application.')
      return
    }
    setWorking(component)
    setNotice(undefined)
    try {
      const result = await bridge.repairRuntime(component)
      setRuntime(result.status)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Local runtime repair failed.')
    } finally {
      setWorking(undefined)
    }
  }, [])

  const agentService: LocalService | undefined = agent ? {
    state: agent.configured ? 'ready' : 'not_configured',
    detail: agent.configured
      ? `${agent.provider} is configured. Chat prefers ${agent.preferred_chat_model} with ${agent.fallback_models} fallback model${agent.fallback_models === 1 ? '' : 's'}.`
      : 'The Agent backend is reachable, but OPENROUTER_API_KEY is not configured on the server. Chat cannot answer until this key is added.',
  } : undefined

  return <div className="scrollbar-thin h-full overflow-y-auto bg-[#151515] p-4"><div className="mx-auto max-w-[680px]"><header className="mb-4 flex items-start justify-between border-b border-white/[0.08] pb-3"><div><p className="font-mono text-[8px] uppercase tracking-[0.14em] text-signal-ice">Settings</p><h1 className="mt-1 text-[15px] font-medium text-white/90">Connections & local runtime</h1><p className="mt-1 text-[10px] leading-4 text-white/46">The agent runs in the cloud; Serena and Graphiti run locally and stay private to this computer.</p></div><button type="button" onClick={() => void refresh()} className="rounded-sm border border-white/[0.1] p-1.5 text-white/52 transition-colors hover:border-signal-ice/30 hover:text-signal-ice" aria-label="Refresh status"><RefreshCw size={12} /></button></header>
    {notice && <div className="mb-3 rounded-md border border-amber-300/25 bg-amber-300/[0.06] px-3 py-2 text-[10px] leading-4 text-amber-100/85">{notice}</div>}
    <div className="grid gap-2.5"><ServiceCard icon={Bot} title="Agent connection" service={agentService} working={false} /><ServiceCard icon={CheckCircle2} title="Local runtime" service={runtime?.runtime} actionLabel={runtime?.paired ? 'Restart service' : undefined} onAction={runtime?.paired ? () => void repair('runtime') : undefined} working={working === 'runtime' || working === 'all'} /><ServiceCard icon={CircleAlert} title="Serena semantic index" service={runtime?.serena} actionLabel="Install / repair Serena" onAction={() => void repair('serena')} working={working === 'serena' || working === 'all'} /><ServiceCard icon={Database} title="Graphiti project memory" service={runtime?.graphiti} actionLabel="Install / start Graphiti" onAction={() => void repair('graphiti')} working={working === 'graphiti' || working === 'all'} /></div>
    <div className="mt-3 rounded-md border border-white/[0.08] bg-white/[0.025] px-3 py-2.5 text-[9px] leading-4 text-white/42">Serena is installed once per computer and indexes the selected local workspace. Graphiti uses one local Neo4j memory profile with separate project namespaces; it requires Docker but is never exposed to the Internet. {runtime?.lastRepairAt ? `Last local repair: ${new Date(runtime.lastRepairAt).toLocaleString()}.` : ''}</div>
  </div></div>
}
