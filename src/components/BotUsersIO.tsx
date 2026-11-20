import React, { useEffect, useRef, useState } from 'react';
import { Upload, Download, Users, Loader2, CheckCircle2, XCircle, FileJson, FileText } from 'lucide-react';
import { apiService, apiErrorMessage, UsersJob } from '../services/apiService';

interface Props {
  botId: string;
  hasToken: boolean;
  showToast: (m: string) => void;
}

const FILTER_OPTS: [string, string][] = [['all', 'All users'], ['active', 'Active users only'], ['blocked', 'Blocked users only'], ['active7d', 'Active in the last 7 days'], ['inactive30d', 'Inactive for 30+ days']];
const FIELD_OPTS: [string, string][] = [['id', 'User ID'], ['name', 'Name'], ['username', 'Username'], ['blocked', 'Blocked by you'], ['botBlocked', 'Blocked the bot'], ['registeredAt', 'Registration date'], ['lastActive', 'Last active'], ['lastMessage', 'Last message'], ['messages', 'Messages count'], ['language', 'Language']];
const fmtEta = (s?: number) => (s === undefined ? '' : s < 60 ? `${s}s left` : `${Math.ceil(s / 60)} min left`);
const fmtSize = (n?: number) => (!n ? '' : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`);

const Bar: React.FC<{ pct: number; tone: string }> = ({ pct, tone }) => (
  <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
    <div className={`h-full rounded-full transition-all duration-500 ${tone}`} style={{ width: `${Math.min(100, Math.max(2, pct))}%` }} />
  </div>
);

export const BotUsersIO: React.FC<Props> = ({ botId, hasToken, showToast }) => {
  const [imp, setImp] = useState<UsersJob | null>(null);
  const [exp, setExp] = useState<UsersJob | null>(null);
  const [fmt, setFmt] = useState<'json' | 'csv' | 'txt'>('csv');
  const [fields, setFields] = useState<string[]>(['id', 'name', 'username', 'blocked', 'registeredAt', 'lastActive']);
  const [flt, setFlt] = useState('all');
  const [busy, setBusy] = useState<'' | 'import' | 'export'>('');
  const fileRef = useRef<HTMLInputElement>(null);
  const done = useRef<Record<string, boolean>>({});

  // pick the progress back up after a reload / tab change
  useEffect(() => {
    let live = true;
    apiService.usersJobs(botId).then((j) => { if (live) { j.import && setImp(j.import); j.export && setExp(j.export); } }).catch(() => {});
    return () => { live = false; };
  }, [botId]);

  const running = imp?.state === 'running' || exp?.state === 'running';
  useEffect(() => {
    if (!running) return;
    const t = setInterval(async () => {
      try {
        if (imp?.state === 'running') {
          const j = await apiService.usersJob(botId, imp.id);
          setImp(j);
          if (j.state !== 'running' && !done.current[j.id]) {
            done.current[j.id] = true;
            showToast(j.state === 'done' ? `Import finished — ${j.imported} users added` : j.state === 'cancelled' ? 'Import cancelled' : j.error || 'Import failed');
            window.dispatchEvent(new CustomEvent('bm_refresh'));
          }
        }
        if (exp?.state === 'running') {
          const j = await apiService.usersJob(botId, exp.id);
          setExp(j);
          if (j.state !== 'running' && !done.current[j.id]) {
            done.current[j.id] = true;
            showToast(j.state === 'done' ? 'Export ready — download it below' : j.error || 'Export cancelled');
          }
        }
      } catch { /* keep trying */ }
    }, 800);
    return () => clearInterval(t);
  }, [running, imp?.id, imp?.state, exp?.id, exp?.state, botId]);

  const pick = async (f?: File | null) => {
    if (!f) return;
    if (f.size > 20 * 1024 * 1024) return showToast('That file is too large (max 20 MB).');
    setBusy('import');
    try { setImp(await apiService.importUsers(botId, f)); showToast('Import started — verifying users with Telegram'); }
    catch (e) { showToast(apiErrorMessage(e, 'Could not import that file.')); }
    finally { setBusy(''); if (fileRef.current) fileRef.current.value = ''; }
  };

  const startExport = async () => {
    setBusy('export');
    try { setExp(await apiService.exportUsers(botId, { format: fmt, fields, filter: flt })); }
    catch (e) { showToast(apiErrorMessage(e, 'Could not start the export.')); }
    finally { setBusy(''); }
  };

  const card = 'p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 space-y-3';
  return (
    <div className="pb-5 border-b border-slate-200 dark:border-slate-800 space-y-3" id="users-import-export">
      <div className="flex items-center gap-2">
        <Users className="w-4 h-4 text-blue-600" />
        <h3 className="text-sm font-bold text-slate-900 dark:text-white">Users — Import &amp; Export</h3>
      </div>
      <p className="text-xs text-slate-500 max-w-2xl">Moving from another platform? Bring your users in, or take a copy of your audience out. Your existing users and bot data are never changed by an import.</p>
      <div className="grid md:grid-cols-2 gap-4">
        {/* IMPORT */}
        <div className={card}>
          <div className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white"><Upload className="w-3.5 h-3.5 text-blue-600" /> Import users</div>
          <ul className="text-[11px] text-slate-500 space-y-0.5 list-disc pl-4">
            <li>Telegram user IDs in a JSON, CSV or TXT file.</li>
            <li>Each ID is verified through Telegram — only reachable users are added (about 10 per second).</li>
            <li>Your bot token must be valid, and users must have started your bot before.</li>
          </ul>
          <input ref={fileRef} type="file" accept=".json,.csv,.txt,text/plain,text/csv,application/json" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          <button
            disabled={!hasToken || busy === 'import' || imp?.state === 'running'}
            onClick={() => fileRef.current?.click()}
            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold text-xs cursor-pointer flex items-center gap-1.5"
          >
            {busy === 'import' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            <span>Choose file &amp; import</span>
          </button>
          {!hasToken && <p className="text-[11px] text-amber-600">Add your bot token in Settings first.</p>}
          {imp && (
            <div className="space-y-1.5" aria-live="polite">
              <Bar pct={imp.percent} tone={imp.state === 'error' ? 'bg-rose-500' : imp.state === 'done' ? 'bg-emerald-500' : 'bg-blue-600'} />
              <div className="flex items-center justify-between text-[11px] text-slate-600 dark:text-slate-300">
                <span className="flex items-center gap-1">
                  {imp.state === 'running' ? <Loader2 className="w-3 h-3 animate-spin" /> : imp.state === 'done' ? <CheckCircle2 className="w-3 h-3 text-emerald-500" /> : <XCircle className="w-3 h-3 text-rose-500" />}
                  {imp.state === 'running' ? `Verifying… ${imp.processed.toLocaleString()} / ${imp.total.toLocaleString()}` : imp.state === 'done' ? 'Import complete' : imp.state === 'cancelled' ? 'Cancelled' : 'Stopped'}
                </span>
                <span>{imp.state === 'running' ? fmtEta(imp.etaSeconds) : ''}</span>
              </div>
              <div className="text-[11px] text-slate-500">
                <b className="text-emerald-600">{(imp.imported ?? 0).toLocaleString()}</b> added · {(imp.existing ?? 0).toLocaleString()} already in your bot · {(imp.unreachable ?? 0).toLocaleString()} unreachable{imp.failed ? ` · ${imp.failed} failed (try again)` : ''}{imp.ignored ? ` · ${imp.ignored} invalid entries skipped` : ''}
              </div>
              {imp.state === 'running' && (
                <button onClick={() => apiService.cancelUsersJob(botId, imp.id).then(setImp).catch(() => {})} className="text-[11px] font-bold text-rose-600 hover:underline cursor-pointer">Cancel import</button>
              )}
            </div>
          )}
        </div>

        {/* EXPORT */}
        <div className={card}>
          <div className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white"><Download className="w-3.5 h-3.5 text-emerald-600" /> Export users</div>
          <ul className="text-[11px] text-slate-500 space-y-0.5 list-disc pl-4">
            <li>Works for bots of any size — a million users export in seconds.</li>
            <li>Download as JSON, CSV or a plain list of IDs (TXT) — choose the columns and which users, with live progress.</li>
          </ul>
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex rounded-xl overflow-hidden border border-slate-300 dark:border-slate-700 text-xs font-bold">
              {(['csv', 'json', 'txt'] as const).map((f) => (
                <button key={f} onClick={() => setFmt(f)} title={f === 'txt' ? 'User IDs only, one per line' : undefined} className={`px-3 py-1.5 flex items-center gap-1 cursor-pointer ${fmt === f ? 'bg-blue-600 text-white' : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300'}`}>
                  {f === 'json' ? <FileJson className="w-3 h-3" /> : <FileText className="w-3 h-3" />}{f.toUpperCase()}
                </button>
              ))}
            </div>
            <select value={flt} onChange={(e) => setFlt(e.target.value)} aria-label="Which users" className="px-2.5 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200">
              {FILTER_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          {fmt === 'txt' ? (
            <p className="text-[11px] text-slate-500">TXT contains only Telegram user IDs, one per line — ready to import into another bot.</p>
          ) : (
            <div>
              <span className="text-[11px] font-bold text-slate-600 dark:text-slate-300">Columns to include</span>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                {FIELD_OPTS.map(([k, l]) => (
                  <label key={k} className="flex items-center gap-1 text-xs font-medium text-slate-700 dark:text-slate-300">
                    <input type="checkbox" disabled={k === 'id'} checked={fields.includes(k)} onChange={(e) => setFields((p) => (e.target.checked ? [...p, k] : p.filter((x) => x !== k)))} className="rounded text-blue-600" />
                    <span>{l}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
          <button
            disabled={busy === 'export' || exp?.state === 'running'}
            onClick={startExport}
            className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-xs cursor-pointer flex items-center gap-1.5"
          >
            {busy === 'export' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            <span>Start export</span>
          </button>
          {exp && (
            <div className="space-y-1.5" aria-live="polite">
              <Bar pct={exp.percent} tone={exp.state === 'error' ? 'bg-rose-500' : 'bg-emerald-500'} />
              <div className="flex items-center justify-between text-[11px] text-slate-600 dark:text-slate-300">
                <span>{exp.state === 'running' ? `Exporting… ${exp.processed.toLocaleString()} / ${exp.total.toLocaleString()}` : exp.state === 'done' ? `${(exp.rows ?? exp.total).toLocaleString()} users · ${fmtSize(exp.size)} · ${exp.format?.toUpperCase()}` : exp.error || 'Cancelled'}</span>
                {exp.state === 'done' && (
                  <button onClick={() => apiService.downloadUsersExport(botId, exp).catch((e) => showToast(apiErrorMessage(e, 'Download failed.')))} className="px-3 py-1 rounded-lg bg-slate-900 dark:bg-white text-white dark:text-slate-900 font-bold flex items-center gap-1 cursor-pointer">
                    <Download className="w-3 h-3" /> Download
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
