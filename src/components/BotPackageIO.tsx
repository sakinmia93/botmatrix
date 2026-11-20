import React, { useRef, useState, useEffect } from 'react';
import { Download, Upload, Loader2, CheckCircle2, AlertTriangle, Package, XCircle } from 'lucide-react';
import { apiService, apiErrorMessage } from '../services/apiService';

interface Props {
  botId: string;
  showToast: (m: string) => void;
  onChanged: () => void;
}

const PARTS: [string, string, string][] = [
  ['commands', 'Commands', 'Code, aliases, admin-only, pinned, folders'],
  ['env', 'Environment variables', 'Keys and (optionally) values'],
  ['settings', 'Bot settings', 'Version, description, category, mini app, speed'],
  ['data', 'Bot database', 'Bot-wide and per-user stored data'],
  ['users', 'Users (IDs)', 'On import, verified through Telegram'],
];

const Bar: React.FC<{ pct: number; tone: string }> = ({ pct, tone }) => (
  <div className="h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
    <div className={`h-full ${tone} transition-all duration-300`} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
  </div>
);

export const BotPackageIO: React.FC<Props> = ({ botId, showToast, onChanged }) => {
  const [fmt, setFmt] = useState<'json' | 'yaml' | 'txt'>('json');
  const [parts, setParts] = useState<string[]>(['commands', 'env', 'settings']);
  const [envValues, setEnvValues] = useState(true);
  const [busy, setBusy] = useState(false);
  const [exp, setExp] = useState<{ state: 'running' | 'done' | 'error'; percent: number; label: string; filename?: string } | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [pick, setPick] = useState<string[]>([]);
  const [replace, setReplace] = useState(false);
  const [result, setResult] = useState<any>(null);
  const ref = useRef<HTMLInputElement>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (tickRef.current) clearInterval(tickRef.current); }, []);

  const doExport = async () => {
    if (busy) return;
    setBusy(true);
    setExp({ state: 'running', percent: 8, label: 'Preparing export…' });
    // Smooth indeterminate-style progress while the blob downloads (fast path for package exports)
    let p = 8;
    if (tickRef.current) clearInterval(tickRef.current);
    tickRef.current = setInterval(() => {
      p = Math.min(92, p + Math.max(1, (92 - p) * 0.12));
      setExp((prev) => (prev && prev.state === 'running' ? { ...prev, percent: p, label: p < 40 ? 'Collecting commands & settings…' : p < 70 ? 'Packing database…' : 'Almost ready…' } : prev));
    }, 180);
    try {
      const fn = await apiService.exportBotPackage(
        botId,
        fmt,
        fmt === 'txt' ? parts.filter((x) => ['commands', 'env', 'settings'].includes(x)) : parts,
        envValues,
      );
      if (tickRef.current) clearInterval(tickRef.current);
      setExp({ state: 'done', percent: 100, label: `Exported · ${fn}`, filename: fn });
      showToast(`Exported ${fn}`);
    } catch (e) {
      if (tickRef.current) clearInterval(tickRef.current);
      setExp({ state: 'error', percent: 100, label: apiErrorMessage(e, 'Export failed.') });
      showToast(apiErrorMessage(e, 'Export failed.'));
    } finally {
      setBusy(false);
    }
  };

  const choose = async (f?: File | null) => {
    if (!f) return;
    setFile(f); setResult(null); setPreview(null);
    try {
      const p = await apiService.importBotPackage(botId, f, { dryRun: true });
      setPreview(p); setPick(p.available || []);
    } catch (e) {
      setFile(null);
      showToast(apiErrorMessage(e, 'That file could not be read.'));
    } finally {
      if (ref.current) ref.current.value = '';
    }
  };

  const apply = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const r = await apiService.importBotPackage(botId, file, { parts: pick, replace });
      setResult(r); setPreview(null); setFile(null);
      showToast(r.skipped?.length ? `Imported — ${r.skipped.length} command(s) skipped` : 'Import complete');
      onChanged();
    } catch (e) {
      showToast(apiErrorMessage(e, 'Import failed.'));
    } finally {
      setBusy(false);
    }
  };

  const togglePart = (k: string) => {
    setParts((prev) => (prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k]));
  };

  return (
    <div className="space-y-4 min-w-0 w-full">
      <div className="flex items-start gap-2 min-w-0">
        <Package className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">Bot — Export &amp; Import</h3>
          <p className="text-xs text-slate-500 mt-0.5">Back up, move or edit your whole bot as a file. The bot token is never included.</p>
        </div>
      </div>

      {/* EXPORT */}
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/40 p-4 space-y-3 min-w-0">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white">
          <Download className="w-3.5 h-3.5 text-emerald-600" /> Export bot
        </div>
        <div className="inline-flex rounded-xl overflow-hidden border border-slate-300 dark:border-slate-700 text-xs font-bold flex-wrap">
          {(['json', 'yaml', 'txt'] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFmt(f)}
              className={`px-3 py-1.5 uppercase cursor-pointer ${fmt === f ? 'bg-blue-600 text-white' : 'bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300'}`}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="space-y-1.5">
          {PARTS.map(([k, label, hint]) => (
            <label key={k} className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={parts.includes(k)}
                disabled={fmt === 'txt' && !['commands', 'env', 'settings'].includes(k)}
                onChange={() => togglePart(k)}
                className="mt-0.5 rounded text-blue-600"
              />
              <span className="min-w-0">
                <b>{label}</b>
                <span className="text-slate-500"> — {hint}</span>
              </span>
            </label>
          ))}
          <label className="flex items-start gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
            <input type="checkbox" checked={envValues} onChange={(e) => setEnvValues(e.target.checked)} className="mt-0.5 rounded text-blue-600" />
            <span>Include variable values <span className="text-slate-500">(untick before sharing the file)</span></span>
          </label>
        </div>
        <button
          type="button"
          disabled={busy || parts.length === 0}
          onClick={doExport}
          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold text-xs cursor-pointer flex items-center gap-1.5"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
          <span>Export bot</span>
        </button>
        {exp && (
          <div className="space-y-1.5" aria-live="polite">
            <Bar pct={exp.percent} tone={exp.state === 'error' ? 'bg-rose-500' : exp.state === 'done' ? 'bg-emerald-500' : 'bg-blue-600'} />
            <div className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
              {exp.state === 'running' ? <Loader2 className="w-3 h-3 animate-spin shrink-0" /> : exp.state === 'done' ? <CheckCircle2 className="w-3 h-3 text-emerald-500 shrink-0" /> : <XCircle className="w-3 h-3 text-rose-500 shrink-0" />}
              <span className="min-w-0 break-words">{exp.label}</span>
            </div>
          </div>
        )}
      </div>

      {/* IMPORT */}
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/40 p-4 space-y-3 min-w-0">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white">
          <Upload className="w-3.5 h-3.5 text-blue-600" /> Import into this bot
        </div>
        <p className="text-[11px] text-slate-500">Choose a JSON, YAML or TXT export. You will see what it contains before anything changes. Commands with code errors are skipped and listed.</p>
        <input ref={ref} type="file" accept=".json,.yaml,.yml,.txt,application/json,text/plain" className="hidden" onChange={(e) => choose(e.target.files?.[0])} />
        <button
          type="button"
          disabled={busy}
          onClick={() => ref.current?.click()}
          className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold text-xs cursor-pointer flex items-center gap-1.5"
        >
          <Upload className="w-3.5 h-3.5" />
          <span>Choose file</span>
        </button>

        {preview && (
          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 space-y-2 text-xs">
            <div className="font-bold text-slate-900 dark:text-white truncate">{file?.name}</div>
            {(preview.summary || []).map((s: string, i: number) => (
              <label key={i} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pick.includes((preview.available || [])[i] || s.split(' ')[0]?.toLowerCase())}
                  onChange={() => {
                    const key = (preview.available || [])[i];
                    if (!key) return;
                    setPick((p) => (p.includes(key) ? p.filter((x) => x !== key) : [...p, key]));
                  }}
                  className="rounded text-blue-600"
                />
                <span>{s}</span>
              </label>
            ))}
            {/* fallback if summary not shaped as above */}
            {!preview.summary && (preview.available || []).map((k: string) => (
              <label key={k} className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={pick.includes(k)} onChange={() => setPick((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]))} className="rounded text-blue-600" />
                <span className="capitalize">{k}</span>
              </label>
            ))}
            <label className="flex items-start gap-2 text-rose-600 dark:text-rose-400 cursor-pointer">
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} className="mt-0.5 rounded text-rose-600" />
              <span>Replace what is there instead of merging <span className="font-normal">(removes commands/variables/data not in the file)</span></span>
            </label>
            <button type="button" disabled={busy || pick.length === 0} onClick={apply} className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold cursor-pointer flex items-center gap-1.5">
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              Apply import
            </button>
          </div>
        )}

        {result && (
          <div className="text-[11px] text-slate-600 dark:text-slate-300 space-y-1">
            <div className="flex items-center gap-1 text-emerald-600 font-bold"><CheckCircle2 className="w-3.5 h-3.5" /> Import applied</div>
            {result.skipped?.length > 0 && (
              <div className="text-amber-600 flex gap-1"><AlertTriangle className="w-3.5 h-3.5 shrink-0" /><span>Skipped: {result.skipped.map((s: any) => `${s.command} (${s.reason})`).join('; ')}</span></div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default BotPackageIO;
