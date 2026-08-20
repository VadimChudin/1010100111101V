import { BrainCircuit, Check, Clock3, FolderGit2, Github, Laptop, Link2, ShieldCheck, X } from 'lucide-react'
import type { DeviceJob, GraphitiEpisodeEnvelope, LocalWorkspace, ProjectDevice, ProjectSource, RepositoryIndex } from '../types'

type Pairing = { pairing_token: string; expires_at: string; name_hint: string }

type RuntimePanelProps = {
  devices: ProjectDevice[]
  episodes: GraphitiEpisodeEnvelope[]
  jobs: DeviceJob[]
  localWorkspaces: LocalWorkspace[]
  source: ProjectSource | null
  repository?: RepositoryIndex
  pairing?: Pairing
  onPair: () => Promise<unknown>
  onQueueIndex: (deviceId: string, workspaceId: string) => Promise<unknown>
  onSelectLocal: (workspaceId: string) => Promise<unknown>
  onSelectGitHub: () => Promise<unknown>
  onApproveJob: (jobId: string, approved: boolean) => Promise<void>
}

const short = (value?: string | null, size = 8) => value ? `${value.slice(0, size)}${value.length > size ? '…' : ''}` : '—'

export default function RuntimePanel({ devices, episodes, jobs, localWorkspaces, source, repository, pairing, onPair, onQueueIndex, onSelectLocal, onSelectGitHub, onApproveJob }: RuntimePanelProps) {
  const online = devices.filter((device) => device.status === 'online').length
  const pendingJobs = jobs.filter((job) => job.status === 'pending_approval')
  const workspaceForDevice = (deviceId: string) => localWorkspaces.find((workspace) => workspace.device_id === deviceId)
  return <aside className="absolute right-4 top-4 z-20 hidden w-[296px] border border-white/[0.10] bg-[#0b1017]/95 p-3 shadow-2xl backdrop-blur-xl xl:block">
    <div className="flex items-start justify-between gap-3 border-b border-white/[0.08] pb-3">
      <div><p className="font-mono text-[9px] uppercase tracking-[0.16em] text-signal-ice">Hybrid runtime</p><h3 className="mt-1 font-display text-sm font-semibold text-white">PC capabilities</h3></div>
      <span className={`rounded-full border px-2 py-1 font-mono text-[8px] uppercase tracking-[0.1em] ${online ? 'border-complete/30 bg-complete/10 text-complete' : 'border-white/10 text-text-dim'}`}>{online}/{devices.length || 0} online</span>
    </div>

    <div className="mt-3 space-y-2">
      {devices.length === 0 ? <p className="rounded border border-dashed border-white/10 p-2 font-mono text-[9px] leading-relaxed text-text-dim">No PC runtime paired. Cloud state remains available; pair a runtime to enable local Serena and Graphiti.</p> : devices.map((device) => <div key={device.id} className="rounded border border-white/[0.08] bg-black/20 p-2">
        <div className="flex items-center justify-between gap-2"><span className="flex min-w-0 items-center gap-2 font-mono text-[10px] text-white"><Laptop size={12} className={device.status === 'online' ? 'text-complete' : 'text-text-dim'} /><span className="truncate">{device.name}</span></span><span className={`font-mono text-[8px] uppercase ${device.status === 'online' ? 'text-complete' : 'text-text-dim'}`}>{device.status}</span></div>
        <p className="mt-1 font-mono text-[8px] text-text-dim">{device.inventory?.branch || 'No workspace'} · {short(device.inventory?.commit_sha)} {device.inventory?.dirty ? '· DIRTY' : ''}</p>
        <p className="mt-1 font-mono text-[8px] text-white/35">Sync {device.last_synced_at ? new Date(device.last_synced_at).toLocaleString() : 'pending'}</p>
        {workspaceForDevice(device.id) && <button disabled={device.status !== 'online'} onClick={() => void onQueueIndex(device.id, workspaceForDevice(device.id)!.id)} className="mt-2 flex w-full items-center justify-center gap-1 border border-white/[0.10] bg-white/[0.03] py-1.5 font-mono text-[8px] uppercase tracking-[0.10em] text-text-dim transition-colors hover:border-signal-ice/30 hover:text-signal-ice disabled:cursor-not-allowed disabled:opacity-40"><Clock3 size={10} /> Request local index</button>}
      </div>)}</div>

    <button onClick={() => void onPair()} className="mt-3 flex w-full items-center justify-center gap-2 border border-signal-ice/25 bg-signal-ice/[0.08] py-2 font-mono text-[9px] uppercase tracking-[0.12em] text-signal-ice transition-colors hover:bg-signal-ice/[0.16]"><Link2 size={12} /> Pair PC runtime</button>
    <div className="mt-3 border-t border-white/[0.08] pt-3"><div className="flex items-center justify-between"><span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim"><FolderGit2 size={12} className="text-signal-ice" /> Project source</span><span className="font-mono text-[8px] text-white/60">{source?.kind === 'paired_local' ? 'LOCAL PC' : source?.kind === 'github_repository' ? 'GITHUB' : 'UNSELECTED'}</span></div>{localWorkspaces.map((local) => <button key={local.id} onClick={() => void onSelectLocal(local.id)} className={`mt-2 w-full rounded border p-2 text-left transition-colors ${source?.local_workspace_id === local.id ? 'border-signal-ice/40 bg-signal-ice/[0.08]' : 'border-white/[0.08] bg-black/20 hover:border-signal-ice/25'}`}><span className="flex items-center gap-2 font-mono text-[9px] text-white"><Laptop size={11} /> {local.display_name}</span><span className="mt-1 block font-mono text-[8px] text-text-dim">{local.inventory.branch} · {local.inventory.tracked_files.toLocaleString()} tracked · local metadata only</span></button>)}{repository && <button onClick={() => void onSelectGitHub()} className={`mt-2 w-full rounded border p-2 text-left transition-colors ${source?.kind === 'github_repository' ? 'border-signal-ice/40 bg-signal-ice/[0.08]' : 'border-white/[0.08] bg-black/20 hover:border-signal-ice/25'}`}><span className="flex items-center gap-2 font-mono text-[9px] text-white"><Github size={11} /> GitHub project map</span><span className="mt-1 block truncate font-mono text-[8px] text-text-dim">{repository.repository_url} · {repository.branch}</span></button>}</div>
    {pairing && <div className="mt-2 rounded border border-signal-ice/25 bg-signal-ice/[0.06] p-2"><p className="font-mono text-[8px] uppercase tracking-[0.12em] text-signal-ice">One-time pairing token</p><code className="mt-1 block break-all font-mono text-[9px] leading-relaxed text-white">{pairing.pairing_token}</code><p className="mt-1 font-mono text-[8px] text-text-dim">Expires {new Date(pairing.expires_at).toLocaleTimeString()}</p></div>}

    <div className="mt-3 border-t border-white/[0.08] pt-3"><div className="flex items-center justify-between"><span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim"><Clock3 size={12} className="text-signal-ice" /> Local semantic jobs</span><span className="font-mono text-[9px] text-white">{pendingJobs.length} pending</span></div>{jobs.slice(0, 3).map((job) => <div key={job.id} className="mt-2 rounded border border-white/[0.08] bg-black/20 p-2"><div className="flex items-center justify-between gap-2"><span className="truncate font-mono text-[8px] uppercase text-white">{job.type.replaceAll('_', ' ')}</span><span className="font-mono text-[8px] text-text-dim">{job.status.replaceAll('_', ' ')}</span></div>{job.status === 'pending_approval' && <div className="mt-2 flex gap-1"><button onClick={() => void onApproveJob(job.id, true)} className="flex flex-1 items-center justify-center gap-1 border border-complete/30 bg-complete/10 py-1 font-mono text-[8px] uppercase text-complete"><Check size={10} /> Approve</button><button onClick={() => void onApproveJob(job.id, false)} className="flex flex-1 items-center justify-center gap-1 border border-alert/30 bg-alert/10 py-1 font-mono text-[8px] uppercase text-alert"><X size={10} /> Reject</button></div>}{job.error && <p className="mt-1 truncate font-mono text-[8px] text-alert">{job.error}</p>}</div>)}{jobs.length === 0 && <p className="mt-2 font-mono text-[8px] text-white/35">Requests remain cloud-visible; execution occurs only after approval and paired-PC delivery.</p>}</div>

    <div className="mt-3 border-t border-white/[0.08] pt-3"><div className="flex items-center justify-between"><span className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim"><BrainCircuit size={12} className="text-violet-300" /> Graphiti memory</span><span className="font-mono text-[9px] text-white">{episodes.length}</span></div>{episodes[0] && <p className="mt-2 truncate font-mono text-[9px] text-white/60">{episodes[0].name}: {episodes[0].content}</p>}<p className="mt-2 flex items-center gap-1 font-mono text-[8px] text-white/35"><ShieldCheck size={10} /> Provenance envelopes sync through cloud state</p></div>
  </aside>
}
