// Dark Mission Control: the chat rail is the operator's narrative view of an active run.
import { FormEvent, useEffect, useRef, useState } from 'react'
import { ArrowUp, Check, Circle, Loader2, Radio, RotateCw, Sparkles, Wrench } from 'lucide-react'
import MessageBubble from './MessageBubble'
import type { AgentEvent, AgentStage, ApprovalMode, ChatMessage, PlanStep } from '../types'

const stageMeta: Array<{ key: AgentStage; label: string; icon: typeof Sparkles }> = [
  { key: 'planning', label: 'Plan', icon: Sparkles },
  { key: 'executing', label: 'Tools', icon: Wrench },
  { key: 'review', label: 'Review', icon: RotateCw },
  { key: 'completed', label: 'Done', icon: Check },
]

export default function Chat({ messages, plan, events, loading, error, stage, connected, runId, onSend, approvalMode, onApprovalModeChange }: { messages: ChatMessage[]; plan: PlanStep[]; events: AgentEvent[]; loading: boolean; error?: string; stage: AgentStage; connected: boolean; runId?: string; onSend: (message: string) => void; approvalMode: ApprovalMode; onApprovalModeChange: (mode: ApprovalMode) => void }) {
  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [messages, events])
  const submit = (event: FormEvent) => { event.preventDefault(); if (draft.trim()) { onSend(draft); setDraft('') } }
  const activeIndex = stage === 'idle' ? -1 : stageMeta.findIndex((item) => item.key === stage)

  return (
    <section className="flex min-h-[620px] flex-1 flex-col overflow-hidden border-r border-white/[0.08] bg-[#0c1117]/90 lg:min-w-[390px] lg:max-w-[540px]">
      <div className="border-b border-white/[0.08] px-5 py-4 sm:px-7">
        <div className="flex items-start justify-between gap-4">
          <div><p className="eyebrow">Conversation rail</p><h2 className="mt-1 font-display text-xl font-semibold tracking-[-0.03em] text-white">Run narrative</h2></div>
          <div className={`flex items-center gap-2 rounded-full border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] ${connected ? 'border-complete/25 bg-complete/10 text-complete' : 'border-alert/25 bg-alert/10 text-alert'}`}><span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-complete live-dot' : 'bg-alert'}`} />{connected ? 'Live link' : 'Reconnecting'}</div>
        </div>
        <label className="mt-4 flex items-center justify-between gap-3 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim"><span>Approval mode</span><select value={approvalMode} onChange={(event) => onApprovalModeChange(event.target.value as ApprovalMode)} disabled={loading} className="max-w-[220px] rounded border border-white/10 bg-[#0a0e13] px-2 py-1 text-[10px] text-white outline-none disabled:opacity-50"><option value="plan">Plan · read only</option><option value="confirm_each">Confirm each action</option><option value="allow_workspace_edits">Allow workspace edits</option><option value="smart_development">Smart development</option><option value="all_approvals_for_run">All approvals for this run</option></select></label>
        <div className="mt-5 flex items-center gap-1">
          {stageMeta.map((item, index) => { const done = activeIndex > index || stage === 'completed'; const active = activeIndex === index; return <div key={item.key} className="flex min-w-0 flex-1 items-center gap-1.5"><div className={`relative grid h-8 w-8 shrink-0 place-items-center rounded-full border font-mono text-[10px] font-semibold ${done ? 'border-complete/40 bg-complete/10 text-complete' : active ? 'border-signal-ice/60 bg-signal-ice/10 text-signal-ice' : 'border-white/10 text-text-dim'}`}>{done ? <Check size={13} /> : active && loading ? <Loader2 size={13} className="animate-spin" /> : `0${index + 1}`}{active && <span className="absolute -inset-1 rounded-full border border-signal-ice/20 signal-pulse" />}</div><span className={`hidden truncate font-mono text-[10px] uppercase tracking-[0.12em] sm:inline ${active ? 'text-white' : 'text-text-dim'}`}>{item.label}</span>{index < stageMeta.length - 1 && <div className={`mx-1 h-px flex-1 ${done ? 'bg-complete/30' : 'bg-white/10'}`} />}</div> })}
        </div>
      </div>
      <div ref={scrollRef} className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-5 py-6 sm:px-7">
        {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
        {loading && <div className="flex items-center gap-3 text-text-dim"><div className="grid h-8 w-8 place-items-center rounded-[10px] border border-signal-ice/20 bg-signal-ice/10 text-signal-ice"><Loader2 size={15} className="animate-spin" /></div><div className="font-mono text-[11px] uppercase tracking-[0.12em]">Agent is working<span className="typing-dots">...</span></div></div>}
        {events.length > 0 && <div className="border-t border-white/[0.07] pt-5"><div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-dim"><Radio size={12} className="text-signal-ice" /> Event trace</div><div className="space-y-2">{events.slice(-5).map((event, index) => <div key={event.id || index} className="flex gap-3 text-[11px] text-text-muted"><Circle size={7} className="mt-1.5 shrink-0 text-signal-ice" /><span>{event.message || event.content || event.text || 'Agent event received'}</span></div>)}</div></div>}
      </div>
      <div className="border-t border-white/[0.08] bg-[#0a0e13]/70 px-5 py-4 sm:px-7">
        {error && <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.1em] text-alert">{error}</p>}
        {runId && <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.1em] text-text-dim">Active run · {runId.slice(0, 18)}</p>}
        <form onSubmit={submit} className="flex items-end gap-2 rounded-[14px] border border-white/[0.12] bg-white/[0.045] p-2 transition-colors focus-within:border-signal-ice/40 focus-within:bg-white/[0.065]">
          <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(event) } }} placeholder="Describe what the agent should do..." rows={2} className="min-h-[46px] flex-1 resize-none bg-transparent px-2 py-1 text-sm leading-6 text-white outline-none placeholder:text-text-dim" aria-label="Message the agent" />
          <button type="submit" disabled={loading || !draft.trim()} className="grid h-10 w-10 shrink-0 place-items-center rounded-[10px] bg-signal-ice text-[#071017] transition-transform hover:bg-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30" aria-label="Send message"><ArrowUp size={17} strokeWidth={2.5} /></button>
        </form>
        <p className="mt-2 text-[10px] text-text-dim">Press Enter to send · Shift + Enter for a new line</p>
      </div>
    </section>
  )
}
