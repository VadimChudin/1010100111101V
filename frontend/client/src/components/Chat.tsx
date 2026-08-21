import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUp, Check, Loader2, Paperclip, ShieldCheck, Sparkles } from 'lucide-react'
import ApprovalCards from './ApprovalCards'
import MessageBubble from './MessageBubble'
import type { AgentEvent, AgentStage, ApprovalGrantScope, ApprovalMode, ApprovalRequest, ChatMessage, PlanStep } from '../types'

function activityCopy(stage: AgentStage, events: AgentEvent[], loading: boolean) {
  if (!loading) return null
  const latest = events.at(-1)
  if (latest?.type === 'conversation.started') return 'Thinking through your message'
  if (latest?.type === 'conversation.completed') return 'Preparing a concise answer'
  if (latest?.type === 'plan.created') return 'Understanding the project task'
  if (latest?.type === 'tool.result') return 'Checking the workspace result'
  if (latest?.type === 'approval.requested') return 'Waiting for your decision'
  if (stage === 'planning') return 'Understanding your request'
  if (stage === 'executing') return 'Working with the project'
  if (stage === 'review') return 'Reviewing the result'
  return 'Working quietly in the background'
}

export default function Chat({ messages, plan: _plan, events, approvals, loading, error, stage, connected, runId, moduleTitle, onSend, onApprovalDecision, onCaptureNote, onCaptureTask, approvalMode, onApprovalModeChange }: { messages: ChatMessage[]; plan: PlanStep[]; events: AgentEvent[]; approvals: ApprovalRequest[]; loading: boolean; error?: string; stage: AgentStage; connected: boolean; runId?: string; moduleTitle?: string; onSend: (message: string) => void; onApprovalDecision: (approvalId: string, approved: boolean, grantScope: ApprovalGrantScope) => void; onCaptureNote: (runId: string, title: string, content: string) => Promise<void>; onCaptureTask: (runId: string, title: string, description: string) => Promise<void>; approvalMode: ApprovalMode; onApprovalModeChange: (mode: ApprovalMode) => void }) {
  const [draft, setDraft] = useState('')
  const [captureState, setCaptureState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [attachments, setAttachments] = useState<Array<{ name: string; excerpt?: string; unsupported?: boolean }>>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const status = useMemo(() => activityCopy(stage, events, loading), [events, loading, stage])

  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }) }, [messages, events, approvals])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!draft.trim() || loading) return
    const attachmentContext = attachments.length ? `\n\n[Local attachments shared with this message]\n${attachments.map((attachment) => attachment.excerpt ? `--- ${attachment.name} ---\n${attachment.excerpt}` : `--- ${attachment.name} ---\nBinary or unsupported attachment remains local; ask the user for a text export or an explicit local-agent task to inspect it.`).join('\n\n')}` : ''
    // The backend accepts 20k characters. Preserve the user's message and fit
    // only as much locally extracted context as remains inside the request cap.
    const contextBudget = Math.max(0, 18_000 - draft.length)
    onSend(`${draft}${attachmentContext.slice(0, contextBudget)}`)
    setDraft('')
    setAttachments([])
  }

  const selectAttachments = async (files: FileList | null) => {
    if (!files?.length) return
    const selected = await Promise.all(Array.from(files).slice(0, 4).map(async (file) => {
      const textLike = file.type.startsWith('text/') || /\.(md|txt|json|ya?ml|toml|xml|csv|ts|tsx|js|jsx|py|go|rs|java|kt|css|html|sql|sh)$/i.test(file.name)
      if (!textLike) return { name: file.name, unsupported: true }
      try {
        const content = await file.text()
        const clipped = content.slice(0, 12_000)
        return { name: file.name, excerpt: `${clipped}${content.length > clipped.length ? '\n[excerpt clipped locally]' : ''}` }
      } catch {
        return { name: file.name, unsupported: true }
      }
    }))
    setAttachments(selected)
  }

  const latestAnswer = [...messages].reverse().find((message) => message.role === 'assistant' && message.runId === runId)?.content || ''
  const capture = async (kind: 'note' | 'task') => {
    if (!runId || loading || !latestAnswer) return
    setCaptureState('saving')
    try {
      if (kind === 'note') await onCaptureNote(runId, 'Conversation decision', latestAnswer)
      else await onCaptureTask(runId, 'Follow up from conversation', latestAnswer)
      setCaptureState('saved')
    } catch {
      setCaptureState('error')
    }
  }

  const askBeforeChanges = approvalMode === 'confirm_each' || approvalMode === 'plan'
  return <section className="flex min-h-0 flex-1 flex-col overflow-hidden bg-transparent">
    <div className="mx-auto flex w-full max-w-none items-center justify-between gap-3 border-b border-white/[0.055] px-4 py-2.5">
      <div><p className="font-mono text-[8px] uppercase tracking-[0.12em] text-white/52">{moduleTitle || 'Conversation'}</p><p className="mt-0.5 text-[10px] text-white/38">Ask a question or describe project work.</p></div>
      <div className={`flex shrink-0 items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.08em] ${connected ? 'text-emerald-300' : 'text-amber-300'}`}><span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-emerald-300 live-dot' : 'bg-amber-300'}`} />{connected ? 'Live' : 'Reconnecting'}</div>
    </div>

    <div ref={scrollRef} className="scrollbar-thin flex-1 overflow-y-auto px-4 pb-4 pt-4">
      <div className="mx-auto flex w-full max-w-none flex-col gap-4">
        {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
        {status && <div className="flex items-center gap-3 pl-1 text-text-dim"><div className="grid h-7 w-7 place-items-center rounded-lg border border-signal-ice/20 bg-signal-ice/[0.08] text-signal-ice"><Loader2 size={13} className="animate-spin" /></div><p className="font-mono text-[10px] uppercase tracking-[0.11em]">{status}<span className="typing-dots">...</span></p></div>}
        {approvals.length > 0 && <div className="rounded-2xl border border-amber-300/20 bg-amber-300/[0.05] p-4"><div className="mb-3 flex items-center gap-2"><ShieldCheck size={14} className="text-amber-200" /><p className="font-mono text-[10px] uppercase tracking-[0.12em] text-amber-100">Your decision is needed</p></div><ApprovalCards approvals={approvals} onDecision={onApprovalDecision} /></div>}
        {runId && !loading && latestAnswer && <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.07] pt-5"><span className="mr-1 font-mono text-[9px] uppercase tracking-[0.12em] text-text-dim">Save context</span><button type="button" disabled={captureState === 'saving'} onClick={() => void capture('note')} className="rounded-lg border border-white/[0.1] px-3 py-1.5 text-xs text-text-muted transition-colors hover:border-signal-ice/30 hover:text-white disabled:opacity-50">Save decision</button><button type="button" disabled={captureState === 'saving'} onClick={() => void capture('task')} className="rounded-lg border border-white/[0.1] px-3 py-1.5 text-xs text-text-muted transition-colors hover:border-signal-ice/30 hover:text-white disabled:opacity-50">Create follow-up</button>{captureState === 'saved' && <span className="flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.1em] text-emerald-300"><Check size={11} />Saved</span>}{captureState === 'error' && <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-rose-300">Could not save</span>}</div>}
      </div>
    </div>

    <div className="border-t border-white/[0.08] bg-[#1c1c1c] px-4 pb-3 pt-2.5">
      <div className="mx-auto w-full max-w-none">
        <div className="mb-2 flex items-center justify-between gap-3"><div className="flex items-center gap-2"><Sparkles size={12} className="text-signal-ice" /><span className="font-mono text-[8px] uppercase tracking-[0.12em] text-text-dim">Mode</span></div><div className="flex rounded-lg border border-white/[0.1] bg-black/10 p-0.5"><button type="button" onClick={() => onApprovalModeChange('confirm_each')} className={`rounded-md px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors ${askBeforeChanges ? 'bg-white/[0.1] text-white' : 'text-text-dim hover:text-white'}`}>Ask</button><button type="button" onClick={() => onApprovalModeChange('allow_workspace_edits')} className={`rounded-md px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors ${!askBeforeChanges ? 'bg-emerald-300/[0.13] text-emerald-200' : 'text-text-dim hover:text-white'}`}>Auto</button></div></div>
        {error && <p className="mb-3 rounded-lg border border-rose-300/20 bg-rose-300/[0.07] px-3 py-2 text-xs text-rose-200">{error}</p>}
        <form onSubmit={submit} className="rounded-lg border border-white/[0.13] bg-white/[0.045] p-1.5 transition-colors focus-within:border-signal-ice/40 focus-within:bg-white/[0.07]">
          <div className="flex items-end gap-2"><input ref={fileInputRef} type="file" multiple className="hidden" onChange={(event) => void selectAttachments(event.target.files)} /><button type="button" aria-label="Attach a local file" title="Attach a local file" onClick={() => fileInputRef.current?.click()} className="grid h-8 w-8 shrink-0 place-items-center rounded-xl text-text-dim transition-colors hover:bg-white/[0.07] hover:text-white"><Paperclip size={17} /></button><textarea data-agent-room-composer value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(event) } }} placeholder="Message Agent Room…" rows={1} className="min-h-[34px] flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-6 text-white outline-none placeholder:text-text-dim" aria-label="Message the agent" /><button type="submit" disabled={loading || !draft.trim()} className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-signal-ice text-[#0a1115] transition-all hover:bg-white active:scale-95 disabled:cursor-not-allowed disabled:opacity-30" aria-label="Send message"><ArrowUp size={17} strokeWidth={2.5} /></button></div>
          {attachments.length > 0 && <div className="mx-2 mt-1.5 flex flex-wrap gap-1.5">{attachments.map((attachment) => <span key={attachment.name} className="max-w-full truncate rounded-md border border-white/[0.1] bg-white/[0.04] px-2 py-1 font-mono text-[8px] uppercase tracking-[0.08em] text-text-dim">{attachment.unsupported ? 'Local only · ' : 'Shared on send · '}{attachment.name}</span>)}</div>}
        </form>
        <p className="mt-1.5 px-1 text-[8px] text-text-dim">Enter to send · Shift + Enter for a new line · Text/code excerpts leave this device only when you send the message.</p>
      </div>
    </div>
  </section>
}
