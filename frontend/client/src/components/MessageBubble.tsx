import { Bot, CircleAlert, UserRound } from 'lucide-react'
import type { ChatMessage } from '../types'

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit' }).format(new Date(timestamp))
}

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'
  return <article className={`message-enter flex gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}><div className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded border ${isUser ? 'border-signal-ice/20 bg-signal-ice/10 text-signal-ice' : isSystem ? 'border-alert/30 bg-alert/10 text-alert' : 'border-white/10 bg-white/[0.045] text-white/62'}`}>{isUser ? <UserRound size={10} /> : isSystem ? <CircleAlert size={10} /> : <Bot size={10} />}</div><div className={`min-w-0 max-w-[92%] ${isUser ? 'text-right' : ''}`}><div className={`mb-1 flex items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.1em] text-white/38 ${isUser ? 'justify-end' : ''}`}><span>{isUser ? 'You' : isSystem ? 'System' : 'Agent'}</span><span className="text-white/20">{formatTime(message.timestamp)}</span></div><div className={`text-[11px] leading-[1.55] ${isUser ? 'text-[#dff8ff]' : isSystem ? 'text-[#f8d9b0]' : 'text-white/76'}`}>{message.content}</div>{message.runId && <div className="mt-1.5 font-mono text-[7px] tracking-[0.08em] text-white/27">RUN {message.runId.slice(0, 14)}</div>}</div></article>
}
