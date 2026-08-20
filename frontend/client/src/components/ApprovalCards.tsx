import { Check, ShieldAlert, X } from 'lucide-react'
import { useState } from 'react'
import type { ApprovalGrantScope, ApprovalRequest } from '../types'

const scopeOptions: Array<{ value: ApprovalGrantScope; label: string }> = [
  { value: 'once', label: 'This action only' },
  { value: 'run', label: 'This tool for this run' },
  { value: 'workspace', label: 'This tool in this workspace' },
  { value: 'all_approved_run', label: 'All approved actions this run' },
]

const describeScope = (approval: ApprovalRequest) => {
  const tool = approval.scope.tool
  const risk = approval.scope.tool_call && typeof approval.scope.tool_call === 'object' && 'risk' in approval.scope.tool_call
    ? (approval.scope.tool_call as { risk?: string }).risk
    : undefined
  return { tool: typeof tool === 'string' ? tool : approval.action_type, risk: typeof risk === 'string' ? risk.replaceAll('_', ' ') : 'protected action' }
}

export default function ApprovalCards({ approvals, onDecision }: { approvals: ApprovalRequest[]; onDecision: (approvalId: string, approved: boolean, grantScope: ApprovalGrantScope) => void }) {
  const [scopes, setScopes] = useState<Record<string, ApprovalGrantScope>>({})
  const [decidingId, setDecidingId] = useState<string>()

  if (approvals.length === 0) return null

  const decide = (approvalId: string, approved: boolean) => {
    setDecidingId(approvalId)
    onDecision(approvalId, approved, scopes[approvalId] || 'once')
    window.setTimeout(() => setDecidingId((current) => current === approvalId ? undefined : current), 1500)
  }

  return <section aria-label="Pending approvals" className="space-y-3 border-t border-white/[0.07] pt-5">
    <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-alert"><ShieldAlert size={13} />Approval required</div>
    {approvals.map((approval) => {
      const detail = describeScope(approval)
      const deciding = decidingId === approval.id
      return <article key={approval.id} className="rounded-xl border border-alert/30 bg-alert/[0.07] p-3 shadow-[0_0_24px_rgba(251,113,133,0.06)]">
        <div className="flex items-start justify-between gap-3"><div><p className="font-mono text-[10px] uppercase tracking-[0.12em] text-alert">Protected tool call</p><h3 className="mt-1 font-display text-sm font-semibold text-white">{detail.tool}</h3><p className="mt-1 text-xs capitalize text-text-muted">Risk: {detail.risk}</p></div><span className="rounded border border-alert/25 px-2 py-1 font-mono text-[9px] uppercase tracking-[0.1em] text-alert">Pending</span></div>
        <label className="mt-3 block font-mono text-[9px] uppercase tracking-[0.1em] text-text-dim">Grant scope<select value={scopes[approval.id] || 'once'} onChange={(event) => setScopes((current) => ({ ...current, [approval.id]: event.target.value as ApprovalGrantScope }))} disabled={deciding} className="mt-1 w-full rounded border border-white/10 bg-[#090d12] px-2 py-2 text-[11px] normal-case tracking-normal text-white outline-none disabled:opacity-50">{scopeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
        <div className="mt-3 grid grid-cols-2 gap-2"><button type="button" disabled={deciding} onClick={() => decide(approval.id, false)} className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/10 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-text-muted transition-colors hover:border-alert/40 hover:text-alert disabled:opacity-50"><X size={13} />Reject</button><button type="button" disabled={deciding} onClick={() => decide(approval.id, true)} className="inline-flex items-center justify-center gap-2 rounded-lg border border-complete/25 bg-complete/10 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.1em] text-complete transition-colors hover:bg-complete/20 disabled:opacity-50"><Check size={13} />{deciding ? 'Saving…' : 'Approve'}</button></div>
      </article>
    })}
  </section>
}
