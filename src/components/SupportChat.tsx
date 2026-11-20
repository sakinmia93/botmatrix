/**
 * Support chat UI — same design as messenger.zip (SimpleChat).
 * Used by user Support tab and Admin → Tickets.
 */
import React, { useEffect, useRef } from 'react';
import { LifeBuoy, User as UserIcon, Send, Check, CheckCheck } from 'lucide-react';

export type ChatMessage = {
  id: string;
  message: string;
  isStaff: boolean;
  authorName?: string;
  createdAt?: string;
  deliveredAt?: string;
  seenAt?: string;
};

type Props = {
  /** Whose perspective: user sees self on right; admin sees self (staff) on right */
  perspective: 'user' | 'admin';
  title: string;
  subtitle?: string;
  status?: string;
  messages: ChatMessage[];
  /** Display name for the end-user (customer) */
  userName: string;
  /** Display name for staff/admin side */
  adminName?: string;
  closed?: boolean;
  sending?: boolean;
  input: string;
  onInput: (v: string) => void;
  onSend: (e: React.FormEvent) => void;
  onBack?: () => void;
  headerRight?: React.ReactNode;
  closedHint?: string;
  /** Other party is typing */
  peerTyping?: boolean;
  peerTypingLabel?: string;
};

function fmtTime(iso?: string) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export const SupportChat: React.FC<Props> = ({
  perspective,
  title,
  subtitle,
  status,
  messages,
  userName,
  adminName = 'Admin',
  closed,
  sending,
  input,
  onInput,
  onSend,
  onBack,
  headerRight,
  closedHint,
  peerTyping,
  peerTypingLabel,
}) => {
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    try {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
    } catch {}
  }, [messages.length, messages[messages.length - 1]?.id]);

  const isMine = (m: ChatMessage) => (perspective === 'admin' ? !!m.isStaff : !m.isStaff);

  return (
    <div
      className="bm-msger flex flex-col w-full min-w-0 max-w-3xl mx-auto border-2 border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 shadow-lg overflow-hidden"
      style={{ height: 'min(75vh, 640px)' }}
    >
      {/* Header */}
      <header className="flex items-center justify-between gap-2 px-3 py-2.5 border-b-2 border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          {onBack && (
            <button type="button" onClick={onBack} className="text-xs font-bold text-blue-600 dark:text-blue-400 cursor-pointer shrink-0">
              ← Back
            </button>
          )}
          <div className="min-w-0">
            <div className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate flex items-center gap-1.5">
              <LifeBuoy className="w-4 h-4 text-blue-500 shrink-0" />
              <span className="truncate">{title}</span>
            </div>
            {subtitle && <div className="text-[10px] text-slate-500 truncate">{subtitle}</div>}
          </div>
          {status && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 shrink-0">
              {status}
            </span>
          )}
        </div>
        {headerRight && <div className="flex items-center gap-1 shrink-0">{headerRight}</div>}
      </header>

      {/* Chat body — messenger patterned background */}
      <main
        className="bm-msger-chat flex-1 overflow-y-auto overflow-x-hidden p-2.5 min-h-0"
        style={{
          backgroundColor: '#fcfcfe',
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80' viewBox='0 0 80 80'%3E%3Cg fill='%23dddddd' fill-opacity='0.35'%3E%3Ccircle cx='10' cy='10' r='2'/%3E%3Ccircle cx='50' cy='30' r='1.5'/%3E%3Ccircle cx='30' cy='60' r='2'/%3E%3C/g%3E%3C/svg%3E\")",
        }}
      >
        {messages.map((m) => {
          const mine = isMine(m);
          const name = m.isStaff ? adminName : userName || m.authorName || 'User';
          const seen = !!m.seenAt;
          const delivered = !!m.deliveredAt || !!m.createdAt;
          return (
            <div
              key={m.id}
              className={`flex items-end mb-2.5 w-full min-w-0 ${mine ? 'flex-row-reverse' : 'flex-row'}`}
            >
              {/* Avatar */}
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-white shadow ${
                  m.isStaff
                    ? 'bg-gradient-to-br from-blue-600 to-indigo-600'
                    : 'bg-violet-500'
                } ${mine ? 'ml-2.5' : 'mr-2.5'}`}
                title={name}
              >
                {m.isStaff ? <LifeBuoy className="w-5 h-5" /> : <UserIcon className="w-5 h-5" />}
              </div>

              {/* Bubble */}
              <div
                className={`max-w-[min(85%,28rem)] min-w-0 overflow-hidden rounded-[15px] px-3.5 py-2.5 shadow-sm ${
                  mine
                    ? 'bg-[#579ffb] text-white rounded-br-none'
                    : 'bg-[#ececec] dark:bg-slate-700 text-slate-800 dark:text-slate-100 rounded-bl-none'
                }`}
              >
                <div className="flex items-center justify-between gap-3 mb-1.5">
                  <span className={`text-[11px] font-bold ${mine ? 'text-white/95' : 'text-slate-700 dark:text-slate-200'}`}>
                    {m.isStaff ? 'Admin' : name}
                  </span>
                  <span className={`text-[10px] shrink-0 ${mine ? 'text-white/75' : 'text-slate-500'}`}>
                    {fmtTime(m.createdAt)}
                  </span>
                </div>
                <div className="text-[13px] leading-relaxed break-words break-all whitespace-pre-wrap [overflow-wrap:anywhere]">
                  {m.message}
                </div>
                {mine && (
                  <div className={`mt-1 flex justify-end ${seen ? 'text-sky-100' : 'text-white/70'}`}>
                    {seen ? (
                      <span title="Seen"><CheckCheck className="w-3.5 h-3.5" /></span>
                    ) : delivered ? (
                      <span title="Delivered"><CheckCheck className="w-3.5 h-3.5 opacity-80" /></span>
                    ) : (
                      <span title="Sent"><Check className="w-3.5 h-3.5" /></span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {peerTyping && (
          <div className="flex items-end mb-2.5 w-full min-w-0">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-white shadow mr-2.5 ${
              perspective === 'user' ? 'bg-gradient-to-br from-blue-600 to-indigo-600' : 'bg-violet-500'
            }`}>
              {perspective === 'user' ? <LifeBuoy className="w-5 h-5" /> : <UserIcon className="w-5 h-5" />}
            </div>
            <div className="rounded-[15px] rounded-bl-none px-3.5 py-2.5 bg-[#ececec] dark:bg-slate-700 text-slate-600 dark:text-slate-200 text-[12px] font-medium shadow-sm">
              <span className="opacity-90">{peerTypingLabel || 'typing'}</span>
              <span className="inline-flex gap-0.5 ml-1 align-middle">
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </main>

      {/* Input */}
      {closed ? (
        <div className="px-3 py-3 text-center text-xs text-slate-500 bg-slate-100 dark:bg-slate-800 border-t-2 border-slate-200 dark:border-slate-700">
          {closedHint || 'This ticket is closed. Neither Admin nor User can reply until it is reopened.'}
        </div>
      ) : (
        <form
          onSubmit={onSend}
          className="flex gap-2 p-2.5 border-t-2 border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 shrink-0"
        >
          <input
            value={input}
            onChange={(e) => onInput(e.target.value)}
            placeholder={sending ? 'Sending…' : 'Enter your message...'}
            disabled={!!sending}
            className="flex-1 min-w-0 rounded px-3 py-2.5 text-sm bg-slate-200 dark:bg-slate-700 text-slate-900 dark:text-slate-100 border-none outline-none focus:ring-2 focus:ring-blue-400/40"
          />
          <button
            type="submit"
            disabled={!!sending || !input.trim()}
            className="px-4 py-2.5 rounded font-bold text-sm text-white bg-[rgb(0,196,65)] hover:bg-[rgb(0,180,50)] disabled:opacity-50 cursor-pointer flex items-center gap-1.5 shrink-0"
          >
            <Send className="w-4 h-4" />
            Send
          </button>
        </form>
      )}
    </div>
  );
};

export default SupportChat;
