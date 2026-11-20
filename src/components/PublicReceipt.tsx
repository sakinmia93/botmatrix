import React, { useEffect, useState } from 'react';
import { BadgeCheck, ShieldAlert } from 'lucide-react';
import { apiService } from '../services/apiService';

/** Public page (no login) that proves a bot transfer happened. Opened from /receipt/<code>. */
export const PublicReceipt: React.FC<{ code: string }> = ({ code }) => {
  const [d, setD] = useState<any>(null);
  useEffect(() => { apiService.getPublicReceipt(code).then(setD).catch(() => setD({ valid: false })); }, [code]);
  const row = (k: string, v: React.ReactNode) => (
    <div className="flex justify-between gap-4 py-2 border-b border-slate-100 dark:border-slate-800 text-sm">
      <span className="text-slate-500">{k}</span><span className="font-semibold text-slate-900 dark:text-white text-right break-all">{v}</span>
    </div>
  );
  const fmt = (s?: string) => (s ? new Date(s).toLocaleString() : '—');
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 shadow-sm">
        {!d ? <p className="text-sm text-slate-500 text-center">Checking receipt…</p> : d.valid ? (
          <>
            <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 font-bold"><BadgeCheck className="w-6 h-6" /> Verified transfer receipt</div>
            <p className="text-xs text-slate-500 mt-1 mb-3">This receipt was signed by BOT MATRIX. Anyone with the link can check it.</p>
            {row('Bot', `${d.botName}${d.botNumericId ? ` (${d.botNumericId})` : ''}`)}
            {row('From', d.from)}
            {row('To', d.to)}
            {row('Status', String(d.status).toUpperCase())}
            {row('Sent', fmt(d.createdAt))}
            {row('Answered', fmt(d.respondedAt))}
            {row('Receipt ID', d.id)}
            {row('Signature', <span className="font-mono text-[11px]">{d.signature}</span>)}
            <p className="text-[11px] text-slate-400 mt-3">{d.algorithm}. Bot tokens and bot data are never shown here.</p>
          </>
        ) : (
          <div className="text-center">
            <ShieldAlert className="w-8 h-8 text-red-500 mx-auto" />
            <p className="font-bold text-slate-900 dark:text-white mt-2">Receipt not valid</p>
            <p className="text-xs text-slate-500 mt-1">This link is wrong or has been altered.</p>
          </div>
        )}
      </div>
    </div>
  );
};
