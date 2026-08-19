// Dark Mission Control: message surfaces keep the narrative rail calm, compact, and state-aware.
import { Bot, CircleAlert, UserRound } from 'lucide-react'
import type { ChatMessage } from '../types'

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit' }).format(new Date(timestamp))
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  return (
    <article className={`message-enter flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border ${isUser ? 'border-signal-ice/20 bg-signal-ice/10 text-signal-ice' : isSystem ? 'border-alert/30 bg-alert/10 text-alert' : 'border-white/10 bg-white/[0.06] text-signal-ice'}`}>
        {isUser ? <UserRound size={15} /> : isSystem ? <CircleAlert size={15} /> : <Bot size={15} />}
      </div>
      <div className={`max-w-[88%] ${isUser ? 'items-end text-right' : ''}`}>
        <div className={`mb-1 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-dim ${isUser ? 'justify-end' : ''}`}>
          <span>{isUser ? 'You' : isSystem ? 'Transport' : 'Agent'}</span>
          <span className="text-white/25">{formatTime(message.timestamp)}</span>
        </div>
        <div className={`rounded-[14px] border px-4 py-3 text-[13px] leading-6 ${isUser ? 'border-signal-ice/20 bg-signal-ice/[0.09] text-[#e9fbff]' : isSystem ? 'border-alert/20 bg-alert/[0.07] text-[#f8d9b0]' : 'border-white/[0.09] bg-white/[0.045] text-text-muted'}`}>
          {message.content}
        </div>
        {message.runId && <div className="mt-2 font-mono text-[10px] tracking-[0.12em] text-text-dim">RUN {message.runId.slice(0, 14)}</div>}
      </div>
    </article>
  )
}
