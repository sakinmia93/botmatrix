import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Database, Search, RefreshCw, Pencil, Trash2, Plus, Copy, X, ChevronLeft, ChevronRight, Users, KeyRound, Loader2 } from 'lucide-react';
import { BotItem } from '../types';
import { apiService, apiErrorMessage } from '../services/apiService';

interface Props {
  bot: BotItem;
  onUpdateBot?: (updated: BotItem) => void;
  showToast: (msg: string) => void;
  initialScope?: 'bot' | 'user';
  hideScopeSwitch?: boolean;
}

type Scope = 'bot' | 'user';
interface Row { id: string; key: string; value: string; type: string; userId?: string; name?: string; username?: string }
interface Draft { isNew: boolean; key: string; value: string; type: string; userId: string }

const TYPE_TONE: Record<string, string> = {
  string: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  number: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300',
  boolean: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
  json: 'bg-violet-100 text-violet-700 dark:bg-violet-950/60 dark:text-violet-300',
};

export const BotDatabaseView: React.FC<Props> = ({ bot, showToast, initialScope = 'bot', hideScopeSwitch = false }) => {
  const [scope, setScope] = useState<Scope>(initialScope);
  const [rows, setRows] = useState<Row[]>([]);
  const [counts, setCounts] = useState({ bot: 0, user: 0, users: 0 });
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [limit, setLimit] = useState(25);
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [userId, setUserId] = useState('');
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [del, setDel] = useState<Row | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const editing = useRef(false);
  editing.current = !!draft || !!del;

  useEffect(() => { const t = setTimeout(() => { setQ(search); setPage(1); }, 300); return () => clearTimeout(t); }, [search]);
  useEffect(() => { setPage(1); }, [scope, userId, limit]);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const r = await apiService.getBotDatabase(bot.id, { scope, page, limit, search: q, userId: scope === 'user' ? userId.trim() : '' });
      setRows(r.rows || []); setCounts(r.counts || { bot: 0, user: 0, users: 0 });
      setTotal(r.total || 0); setPages(r.totalPages || 1);
    } catch (e) { if (!quiet) showToast(apiErrorMessage(e, 'Could not load the database.')); }
    finally { setLoading(false); }
  }, [bot.id, scope, page, limit, q, userId]);

  useEffect(() => { load(); }, [load]);
  // live: re-read every 5 s (paused while editing / tab hidden)
  useEffect(() => {
    const t = setInterval(() => { if (!document.hidden && !editing.current) load(true); }, 5000);
    return () => clearInterval(t);
  }, [load]);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    setSaving(true);
    try {
      await apiService.saveBotDatabaseRow(bot.id, { scope, key: draft.key.trim(), value: draft.value, type: draft.type, userId: scope === 'user' ? draft.userId.trim() : undefined });
      showToast(draft.isNew ? 'Record added' : 'Record updated');
      setDraft(null); load(true);
    } catch (err) { showToast(apiErrorMessage(err, 'Could not save.')); }
    finally { setSaving(false); }
  };
  const remove = async () => {
    if (!del) return;
    try {
      await apiService.deleteBotDatabaseRow(bot.id, { scope, key: del.key, userId: scope === 'user' ? del.userId : undefined });
      showToast('Record deleted'); setDel(null); load(true);
    } catch (err) { showToast(apiErrorMessage(err, 'Could not delete.')); setDel(null); }
  };

  const chip = 'px-3 py-1 rounded-xl text-xs font-bold border';
  const inp = 'w-full px-3 py-2 rounded-xl text-sm bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30';

  return (
    <div className="glass-panel p-5 sm:p-6 rounded-3xl space-y-5">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-white shrink-0"><Database className="w-5 h-5" /></div>
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              Bot Database
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />Live</span>
            </h2>
            <p className="text-xs text-slate-500">Everything your commands save with <code className="font-mono">Bot.saveData</code> and <code className="font-mono">User.saveData</code>, updated as it happens.</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`${chip} bg-blue-50 dark:bg-blue-950/50 border-blue-200 dark:border-blue-900/50 text-blue-700 dark:text-blue-300`}>{counts.bot.toLocaleString()} bot keys</span>
          <span className={`${chip} bg-violet-50 dark:bg-violet-950/50 border-violet-200 dark:border-violet-900/50 text-violet-700 dark:text-violet-300`}>{counts.user.toLocaleString()} user keys · {counts.users.toLocaleString()} users</span>
          <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer"><RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /></button>
          <button onClick={() => setDraft({ isNew: true, key: '', value: '', type: 'string', userId: '' })} className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer"><Plus className="w-3.5 h-3.5" />Add record</button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className={`${hideScopeSwitch ? 'hidden' : 'inline-flex'} rounded-xl overflow-hidden border border-slate-300 dark:border-slate-700 text-xs font-bold`}>
          {([['bot', 'Bot data', KeyRound], ['user', 'User data', Users]] as const).map(([k, l, Icon]) => (
            <button key={k} onClick={() => setScope(k)} className={`px-4 py-2 flex items-center gap-1.5 cursor-pointer ${scope === k ? 'bg-blue-600 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300'}`}><Icon className="w-3.5 h-3.5" />{l}</button>
          ))}
        </div>
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search keys and values…" className={`${inp} pl-9`} />
        </div>
        {scope === 'user' && <input value={userId} onChange={(e) => setUserId(e.target.value.replace(/\D/g, ''))} placeholder="Telegram user ID" className={`${inp} !w-44`} />}
      </div>

      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-x-auto">
        <table className="w-full text-left text-xs min-w-[640px]">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 uppercase tracking-wide text-[10px]">
            <tr>{scope === 'user' && <th className="px-3 py-2.5">User</th>}<th className="px-3 py-2.5">Key</th><th className="px-3 py-2.5">Value</th><th className="px-3 py-2.5">Type</th><th className="px-3 py-2.5 text-right">Actions</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
            {loading && !rows.length ? (
              <tr><td colSpan={5} className="px-3 py-10 text-center text-slate-500"><Loader2 className="w-5 h-5 animate-spin inline" /></td></tr>
            ) : !rows.length ? (
              <tr><td colSpan={5} className="px-3 py-12 text-center text-slate-500">
                {q || userId ? 'No records match your search.' : scope === 'bot' ? 'No bot data yet. It appears here as soon as a command saves something with Bot.saveData.' : 'No user data yet. It appears here as soon as a command saves something with User.saveData.'}
              </td></tr>
            ) : rows.map((r) => {
              const k = `${r.userId || ''}:${r.key}`;
              return (
                <tr key={r.id + k} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  {scope === 'user' && <td className="px-3 py-2.5"><div className="font-semibold text-slate-800 dark:text-slate-200 truncate max-w-[160px]">{r.name || '—'}</div><div className="font-mono text-[10px] text-slate-500">{r.userId}{r.username ? ` · ${r.username}` : ''}</div></td>}
                  <td className="px-3 py-2.5 font-mono font-bold text-slate-900 dark:text-white break-all">{r.key}</td>
                  <td className="px-3 py-2.5 font-mono text-slate-700 dark:text-slate-300 max-w-[360px]">
                    <button onClick={() => setOpen(open === k ? null : k)} className="text-left w-full cursor-pointer" title="Click to expand">
                      <span className={open === k ? 'whitespace-pre-wrap break-all block' : 'truncate block'}>{r.value === '' ? <span className="italic text-slate-400">empty</span> : r.value}</span>
                    </button>
                  </td>
                  <td className="px-3 py-2.5"><span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${TYPE_TONE[r.type] || TYPE_TONE.string}`}>{r.type}</span></td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    <button onClick={() => { navigator.clipboard?.writeText(r.value); showToast('Value copied'); }} title="Copy value" className="p-1.5 rounded-lg text-slate-500 hover:text-blue-600 cursor-pointer"><Copy className="w-3.5 h-3.5" /></button>
                    <button onClick={() => setDraft({ isNew: false, key: r.key, value: r.value, type: r.type, userId: r.userId || '' })} title="Edit" className="p-1.5 rounded-lg text-slate-500 hover:text-blue-600 cursor-pointer"><Pencil className="w-3.5 h-3.5" /></button>
                    <button onClick={() => setDel(r)} title="Delete" className="p-1.5 rounded-lg text-slate-500 hover:text-rose-600 cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-400">
        <span>{total.toLocaleString()} record{total === 1 ? '' : 's'}</span>
        <div className="flex items-center gap-2">
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} aria-label="Rows per page" className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700">{[10, 25, 50, 100, 500, 1000].map((n) => <option key={n} value={n}>{n} / page</option>)}</select>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page" className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 disabled:opacity-40 cursor-pointer"><ChevronLeft className="w-4 h-4" /></button>
          <span className="font-bold">{page} / {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page" className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 disabled:opacity-40 cursor-pointer"><ChevronRight className="w-4 h-4" /></button>
        </div>
      </div>

      {draft && (
        <div className="fixed inset-0 z-[200] bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setDraft(null)}>
          <form onSubmit={save} onClick={(e) => e.stopPropagation()} className="w-full max-w-lg rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 space-y-3 shadow-2xl">
            <div className="flex items-center justify-between"><h3 className="text-base font-bold text-slate-900 dark:text-white">{draft.isNew ? 'Add' : 'Edit'} {scope === 'bot' ? 'bot' : 'user'} record</h3><button type="button" onClick={() => setDraft(null)} aria-label="Close" className="p-1 cursor-pointer"><X className="w-4 h-4" /></button></div>
            {scope === 'user' && <div><label className="text-xs font-bold text-slate-600 dark:text-slate-300">Telegram user ID</label><input required disabled={!draft.isNew} value={draft.userId} onChange={(e) => setDraft({ ...draft, userId: e.target.value.replace(/\D/g, '') })} className={inp} /></div>}
            <div><label className="text-xs font-bold text-slate-600 dark:text-slate-300">Key</label><input required disabled={!draft.isNew} value={draft.key} onChange={(e) => setDraft({ ...draft, key: e.target.value })} className={`${inp} font-mono`} /></div>
            <div><label className="text-xs font-bold text-slate-600 dark:text-slate-300">Type</label>
              <select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })} className={inp}>{['string', 'number', 'boolean', 'json'].map((t) => <option key={t}>{t}</option>)}</select></div>
            <div><label className="text-xs font-bold text-slate-600 dark:text-slate-300">Value</label><textarea rows={5} value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} className={`${inp} font-mono`} /></div>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setDraft(null)} className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs font-bold cursor-pointer">Cancel</button>
              <button disabled={saving} className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold cursor-pointer disabled:opacity-60">{saving ? 'Saving…' : 'Save'}</button>
            </div>
          </form>
        </div>
      )}
      {del && (
        <div className="fixed inset-0 z-[200] bg-slate-950/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={() => setDel(null)}>
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-sm rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 space-y-3 shadow-2xl">
            <h3 className="text-base font-bold text-slate-900 dark:text-white">Delete this record?</h3>
            <p className="text-xs text-slate-600 dark:text-slate-300"><code className="font-mono font-bold">{del.key}</code>{del.userId ? ` for user ${del.userId}` : ''} will be removed. Commands that read it will get nothing.</p>
            <div className="flex justify-end gap-2"><button onClick={() => setDel(null)} className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs font-bold cursor-pointer">Cancel</button><button onClick={remove} className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold cursor-pointer">Delete</button></div>
          </div>
        </div>
      )}
    </div>
  );
};
