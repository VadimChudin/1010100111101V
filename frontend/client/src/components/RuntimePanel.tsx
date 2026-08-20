import { BrainCircuit, Laptop, Link2, RefreshCw, ShieldCheck } from 'lucide-react'
import type { GraphitiEpisodeEnvelope, ProjectDevice } from '../types'

type Pairing = { pairing_token: string; expires_at: string; name_hint: string }

type RuntimePanelProps = {
  devices: ProjectDevice[]
  episodes: GraphitiEpisodeEnvelope[]
  pairing?: Pairing
  onPair: () => Promise<unknown>
}

const short = (value?: string | null, size = 8) => value ? `${value.slice(0, size)}${value.length > size ? '…' : ''}` : '—'

export default function RuntimePanel({ devices, episodes, pairing, onPair }: RuntimePanelProps) {
  const online = devices.filter((device) => device.status === 'online').length
  return <aside className="absolute right-4 top-4 z-20 hidden w-[296px] border border-white/[0.10] bg-[#0b1017]/95 p-3 shadow-2xl backdrop-blur-xl 2xl:block">
    <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-3">
      <div><p className="font-mono text-[9px] uppercase tracking-[0.16em] text-signal-ice">Hybrid runtime</p><h3 className="mt-1 font-display text-sm font-semibold text-white">PC capabilities</h3></div>
      <span className={`rounded-full border px-2 py-1 font-mono text-[8px] uppercase tracking-[0.1em] ${online ? 'border-complete/30 bg-complete/10 text-complete' : 'border-white/10 text-text-dim'}`}>{online}/{devices.length || 0} online</span>
    </div>

    <div className="mt-3 space-y-2">
      {devices.length === 0 ? <p className="rounded border border-dashed border-white/10 p-2 font-mono text-[9px] leading-relaxed text-text-dim">No PC runtime paired. Cloud state remains available; pair a runtime to enable local Serena and Graphiti.</p> : devices.map((device) => <div key={device.id} className="rounded border border-white/[0.08] bg-black/20 p-2">
        <div className="flex items-center justify-between gap-2"><span className="flex min-w-0 items-center gap-2 font-mono text-[10px] text-white"><Laptop size={12} className={device.status === 'online' ? 'text-complete' : 'text-text-dim'} /><span className="truncate">{device.name}</span></span><span className={`font-mono text-[8px] uppercase ${device.status === 'online' ? 'text-complete' : 'text-text-dim'}`}>{device.status}</span></div>
        <p className="mt-1 font-mono text-[8px] text-text-dim">{device.inventory?.branch || 'No workspace'} · {short(device.inventory?.commit_sha)} {device.inventory?.dirty ? '· DIRTY' : ''}</p>
        <p className="mt-1 font-mono text-[8px] text-white/35">Sync {device.last_synced_at ? new Date(device.last_synced_at).toLocaleString() : 'pending'}</p>
      </div>)}</div>

    <button onClick={() => void onPair()} className="mt-3 flex w-full items-center justify-center gap-2 border border-signal-ice/25 bg-signal-ice/[0.08] py-2 font-mono text-[9px] uppercase tracking-[0.12em] text-signal-ice transition-colors hover:bg-signal-ice/[0.16]"><Link2 size={12} /> Pair PC runtime</button>
    {pairing && <div className="mt-2 rounded border border-signal-ice/25 bg-signal-ice/[0.06] p-2"><p className="font-mono text-[8px] uppercase tracking-[0.12em] text-signal-ice">One-time pairing token</p><code className="mt-1 block break-all font-mono text-[9px] leading-relaxed text-white">{pairing.pairing_token}</code><p className="mt-1 font-mono text-[8px] text-text-dim">Expires {new Date(pairing.expires_at).toLocaleTimeString()}</p></div>}

    <div className="mt-3 border-t border-white/[0.08] pt-3"><div className="flex items-center justify-between"><span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim"><BrainCircuit size={12} className="text-violet-300" /> Graphiti memory</span><span className="font-mono text-[9px] text-white">{episodes.length}</span></div>{episodes[0] && <p className="mt-2 truncate font-mono text-[9px] text-white/60">{episodes[0].name}: {episodes[0].content}</p>}<p className="mt-2 flex items-center gap-1 font-mono text-[8px] text-white/35"><ShieldCheck size={10} /> Provenance envelopes sync through cloud state</p></div>
  </aside>
}
