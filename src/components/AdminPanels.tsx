import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  Cpu, MemoryStick, HardDrive, Network, Activity, Server, Gauge, ShieldCheck, ShieldAlert, Database, ScrollText, Skull, Zap,
  Play, Square, RotateCw, Search, Download, Wrench, CheckCircle2, AlertTriangle, XCircle, Clock, Users as UsersIcon, Bot as BotIcon, Flame,
} from 'lucide-react';
import { apiService } from '../services/apiService';
import { ConfirmationModal } from './ConfirmationModal';

export type Lang = 'en' | 'bn';
export const T: Record<string, [string, string]> = {
  server: ['Server', 'সার্ভার'], fleet: ['Bot fleet', 'বট ফ্লিট'], overview: ['Overview', 'ওভারভিউ'], users: ['Users', 'ইউজার'], plans: ['Plans', 'প্ল্যান'],
  database: ['Database', 'ডাটাবেস'], logs: ['Live logs', 'লাইভ লগ'], security: ['Security', 'সিকিউরিটি'], store: ['Store', 'স্টোর'], settings: ['Settings', 'সেটিংস'],
  tickets: ['Tickets', 'টিকিট'], cpu: ['CPU', 'সিপিইউ'], ram: ['Memory', 'র‍্যাম'], disk: ['Disk', 'ডিস্ক'], net: ['Network', 'নেটওয়ার্ক'], load: ['Load average', 'লোড অ্যাভারেজ'],
  uptime: ['Uptime', 'আপটাইম'], cores: ['Per-core load', 'কোর অনুযায়ী লোড'], proc: ['This server process', 'এই সার্ভার প্রসেস'], running: ['Bots running', 'চালু বট'],
  cmdmin: ['Commands / min', 'কমান্ড / মিনিট'], errh: ['Errors (1h)', 'এরর (১ ঘণ্টা)'], radar: ['Damage radar', 'ক্ষতিকর বট রাডার'], speed: ['Response speed', 'রেসপন্স স্পিড'],
  stop: ['Stop', 'বন্ধ'], restart: ['Restart', 'রিস্টার্ট'], start: ['Start', 'চালু'], why: ['Why?', 'কেন?'], scan: ['Scan now', 'এখনই স্ক্যান'], score: ['Security score', 'সিকিউরিটি স্কোর'],
  alerts: ['Alerts', 'সতর্কতা'], sql: ['Read-only SQL console', 'রিড-অনলি SQL কনসোল'], run: ['Run', 'চালান'], title: ['Admin control panel', 'অ্যাডমিন কন্ট্রোল প্যানেল'],
};
export const t = (k: string, l: Lang) => (T[k] ? T[k][l === 'bn' ? 1 : 0] : k);

const errMsg = (e: any) => e?.response?.data?.error || e?.message || 'Something went wrong';
export const fmtBytes = (n: number) => {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${u[i]}`;
};
const fmtDur = (s: number) => { const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60); return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m ${s % 60}s`; };
const tone = (p: number) => (p >= 90 ? '#ef4444' : p >= 70 ? '#f59e0b' : '#10b981');
const card = 'rounded-3xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-sm';
const btn = 'px-3 py-1.5 rounded-xl text-[11px] font-bold cursor-pointer disabled:opacity-50 transition-all active:scale-95';

/** Animated ring gauge. */
const Ring: React.FC<{ pct: number; label: string; sub?: string; icon: React.ReactNode; grad: [string, string] }> = ({ pct, label, sub, icon, grad }) => {
  const r = 46, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0));
  const id = useMemo(() => 'g' + Math.random().toString(36).slice(2, 8), []);
  return (
    <motion.div whileHover={{ y: -3 }} className="relative rounded-3xl p-4 overflow-hidden text-white shadow-lg" style={{ background: `linear-gradient(135deg, ${grad[0]}, ${grad[1]})` }}>
      <div className="absolute -right-6 -top-6 w-28 h-28 rounded-full bg-white/10 blur-xl" />
      <div className="flex items-center gap-4 relative">
        <svg width="110" height="110" viewBox="0 0 110 110" className="shrink-0">
          <defs><linearGradient id={id} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#fff" /><stop offset="1" stopColor="#ffffffaa" /></linearGradient></defs>
          <circle cx="55" cy="55" r={r} fill="none" stroke="#ffffff30" strokeWidth="10" />
          <motion.circle cx="55" cy="55" r={r} fill="none" stroke={`url(#${id})`} strokeWidth="10" strokeLinecap="round" transform="rotate(-90 55 55)"
            strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - p / 100) }} transition={{ duration: 0.8, ease: 'easeOut' }} />
          <text x="55" y="60" textAnchor="middle" fontSize="22" fontWeight="900" fill="#fff">{p.toFixed(0)}%</text>
        </svg>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-xs font-black uppercase tracking-wider opacity-90">{icon}{label}</div>
          {sub && <div className="text-[11px] opacity-90 mt-1 leading-snug">{sub}</div>}
        </div>
      </div>
    </motion.div>
  );
};

/** Tiny SVG area chart. */
const Spark: React.FC<{ data: number[]; color: string; max?: number; h?: number }> = ({ data, color, max, h = 56 }) => {
  const w = 300; const m = max || Math.max(1, ...data);
  const pts = data.map((v, i) => `${(i / Math.max(1, data.length - 1)) * w},${h - (Math.min(v, m) / m) * (h - 4) - 2}`);
  const id = useMemo(() => 's' + Math.random().toString(36).slice(2, 8), []);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" preserveAspectRatio="none" style={{ height: h }}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={color} stopOpacity="0.45" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      {pts.length > 1 && <><polygon points={`0,${h} ${pts.join(' ')} ${w},${h}`} fill={`url(#${id})`} /><polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" /></>}
    </svg>
  );
};

const Bar: React.FC<{ pct: number; color?: string }> = ({ pct, color }) => (
  <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
    <motion.div className="h-full rounded-full" style={{ background: color || tone(pct) }} initial={{ width: 0 }} animate={{ width: `${Math.min(100, pct)}%` }} transition={{ duration: 0.6 }} />
  </div>
);

// ------------------------------------------------------------------------------------------ SERVER
export const ServerPanel: React.FC<{ lang: Lang }> = ({ lang }) => {
  const [d, setD] = useState<any>(null); const [e, setE] = useState('');
  useEffect(() => {
    let alive = true;
    const go = () => apiService.adminGet('server').then((r) => { if (alive) setD(r); }).catch((x) => alive && setE(errMsg(x)));
    go(); const id = setInterval(go, 3000); return () => { alive = false; clearInterval(id); };
  }, []);
  if (e) return <p className="text-xs text-red-500">{e}</p>;
  if (!d) return <p className="text-xs text-slate-500">Loading…</p>;
  const h = d.history || [];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <Ring pct={d.cpu} label={t('cpu', lang)} icon={<Cpu className="w-3.5 h-3.5" />} grad={['#6366f1', '#8b5cf6']} sub={`${d.cpuCount} cores · load ${d.load.join(' / ')}`} />
        <Ring pct={d.mem.pct} label={t('ram', lang)} icon={<MemoryStick className="w-3.5 h-3.5" />} grad={['#06b6d4', '#3b82f6']} sub={`${fmtBytes(d.mem.used)} of ${fmtBytes(d.mem.total)} · cache ${fmtBytes(d.mem.cached)}${d.mem.swapTotal ? ` · swap ${fmtBytes(d.mem.swapUsed)}` : ''}`} />
        <Ring pct={d.disk.pct} label={t('disk', lang)} icon={<HardDrive className="w-3.5 h-3.5" />} grad={['#f59e0b', '#ef4444']} sub={`${fmtBytes(d.disk.used)} used · ${fmtBytes(d.disk.free)} free`} />
        <motion.div whileHover={{ y: -3 }} className="rounded-3xl p-4 text-white shadow-lg relative overflow-hidden" style={{ background: 'linear-gradient(135deg,#10b981,#0ea5e9)' }}>
          <div className="absolute -right-6 -top-6 w-28 h-28 rounded-full bg-white/10 blur-xl" />
          <div className="flex items-center gap-1.5 text-xs font-black uppercase tracking-wider opacity-90"><Network className="w-3.5 h-3.5" />{t('net', lang)}</div>
          <div className="mt-3 text-sm font-mono font-bold">↓ {fmtBytes(d.net.rxPerSec)}/s</div>
          <div className="text-sm font-mono font-bold">↑ {fmtBytes(d.net.txPerSec)}/s</div>
          <div className="mt-2 opacity-90"><Spark data={h.map((x: any) => x.rx + x.tx)} color="#ffffff" h={34} /></div>
        </motion.div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[[t('uptime', lang), fmtDur(d.uptimeSec), <Clock key="a" className="w-4 h-4" />, 'from-violet-500 to-fuchsia-500'],
          [t('running', lang), `${d.bots.running} / ${d.bots.total}`, <BotIcon key="b" className="w-4 h-4" />, 'from-sky-500 to-indigo-500'],
          [t('cmdmin', lang), d.commandsPerMin, <Zap key="c" className="w-4 h-4" />, 'from-amber-500 to-orange-500'],
          [t('errh', lang), d.errorsLastHour, <Flame key="d" className="w-4 h-4" />, 'from-rose-500 to-red-500'],
          ['Python', d.python, <Server key="e" className="w-4 h-4" />, 'from-emerald-500 to-teal-500']].map(([k, v, ic, g]: any) => (
          <motion.div key={k} whileHover={{ y: -2 }} className={`rounded-2xl p-3 text-white bg-gradient-to-br ${g} shadow`}>
            <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider opacity-90">{ic}{k}</div>
            <div className="text-xl font-black mt-1">{v}</div>
          </motion.div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className={card}>
          <div className="text-xs font-black mb-2 text-slate-700 dark:text-slate-300">{t('cpu', lang)} · {t('ram', lang)} <span className="font-normal text-slate-400">(last 3 min)</span></div>
          <Spark data={h.map((x: any) => x.cpu)} color="#6366f1" max={100} />
          <Spark data={h.map((x: any) => x.memPct)} color="#06b6d4" max={100} />
        </div>
        <div className={card}>
          <div className="text-xs font-black mb-2 text-slate-700 dark:text-slate-300">{t('cores', lang)}</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            {(d.cores.length ? d.cores : [d.cpu]).map((c: number, i: number) => (
              <div key={i}><div className="flex justify-between text-[10px] font-bold text-slate-500"><span>Core {i + 1}</span><span>{c.toFixed(0)}%</span></div><Bar pct={c} /></div>
            ))}
          </div>
          <div className="text-xs font-black mt-4 mb-1 text-slate-700 dark:text-slate-300">{t('proc', lang)}</div>
          <div className="text-[11px] text-slate-500 font-mono">PID {d.process.pid} · RSS {fmtBytes(d.process.rss)} · {d.process.threads} threads · {d.process.openFiles} open files</div>
        </div>
      </div>
    </div>
  );
};

// ------------------------------------------------------------------------------------------ FLEET
const SPEED: Record<string, [string, string]> = {
  ultra: ['Ultra fast  <50 ms', '#10b981'], normal: ['Normal  50–500 ms', '#3b82f6'], slow: ['Slow  500–1500 ms', '#f59e0b'], critical: ['Critical  >1500 ms', '#ef4444'], idle: ['Idle', '#94a3b8'],
};
const FLAG: Record<string, string> = { 'heavy-load': 'Heavy load', 'high-errors': 'Many errors', 'critical-slow': 'Critical slow', slow: 'Slow', flooding: 'Flooding' };

export const FleetPanel: React.FC<{ lang: Lang }> = ({ lang }) => {
  const [hours, setHours] = useState(24);
  const [d, setD] = useState<any>(null); const [e, setE] = useState('');
  const [diag, setDiag] = useState<any>(null);
  const [ask, setAsk] = useState<{ bot: any; action: string } | null>(null);
  const [msg, setMsg] = useState('');
  const load = useCallback(() => apiService.adminGet(`fleet?hours=${hours}`).then(setD).catch((x) => setE(errMsg(x))), [hours]);
  useEffect(() => { load(); const id = setInterval(load, 8000); return () => clearInterval(id); }, [load]);
  const why = async (b: any) => { try { setDiag(await apiService.adminGet(`fleet/${b.id}/diagnose?hours=${hours}`)); } catch (x) { setMsg(errMsg(x)); } };
  const act = async () => {
    if (!ask) return; const a = ask; setAsk(null);
    try { await apiService.adminPost(`fleet/${a.bot.id}/action`, { action: a.action }); setMsg(`${a.bot.name}: ${a.action} done`); load(); } catch (x) { setMsg(errMsg(x)); }
  };
  if (e) return <p className="text-xs text-red-500">{e}</p>;
  if (!d) return <p className="text-xs text-slate-500">Loading…</p>;
  const maxBusy = Math.max(1, ...d.bots.map((b: any) => b.busyMs));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1.5">{[1, 24, 168, 720].map((h) => (
          <button key={h} onClick={() => setHours(h)} className={`${btn} ${hours === h ? 'bg-indigo-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'}`}>{h === 1 ? '1h' : h === 24 ? '24h' : h === 168 ? '7d' : '30d'}</button>))}
        </div>
        {msg && <span className="text-[11px] text-blue-600 font-bold">{msg}</span>}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {Object.entries(SPEED).map(([k, [label, color]]) => (
          <div key={k} className="rounded-2xl p-3 text-white shadow" style={{ background: `linear-gradient(135deg, ${color}, ${color}bb)` }}>
            <div className="text-[10px] font-black uppercase tracking-wide opacity-90">{label}</div>
            <div className="text-2xl font-black">{d.speedCounts[k] || 0}</div>
          </div>))}
      </div>
      <div className={card + ' !border-rose-200 dark:!border-rose-900/60'}>
        <div className="flex items-center gap-2 text-sm font-black text-rose-600 mb-2"><Skull className="w-4 h-4" />{t('radar', lang)}</div>
        {d.damaging.length === 0 ? <p className="text-xs text-emerald-600 font-bold flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> No bot is hurting the server right now.</p> : (
          <div className="space-y-2">{d.damaging.map((b: any) => (
            <div key={b.id} className="flex flex-wrap items-center gap-2 p-2.5 rounded-2xl bg-rose-50 dark:bg-rose-950/30 text-xs">
              <b className="min-w-0 truncate">{b.name}</b><span className="text-slate-500">{b.owner}</span>
              {b.flags.map((f: string) => <span key={f} className="px-2 py-0.5 rounded-full bg-rose-600 text-white text-[10px] font-bold">{FLAG[f] || f}</span>)}
              <span className="ml-auto flex gap-1.5">
                <button className={`${btn} bg-slate-800 text-white`} onClick={() => why(b)}>{t('why', lang)}</button>
                <button className={`${btn} bg-rose-600 text-white`} onClick={() => setAsk({ bot: b, action: 'stop' })}>{t('stop', lang)}</button>
              </span>
            </div>))}</div>)}
      </div>
      <div className={card + ' overflow-x-auto'}>
        <table className="w-full text-xs">
          <thead><tr className="text-left text-[10px] uppercase tracking-wider text-slate-400"><th className="pb-2">Bot</th><th>Owner</th><th>Runs</th><th>Avg / p95</th><th>Errors</th><th className="w-40">Load</th><th></th></tr></thead>
          <tbody>{d.bots.map((b: any) => (
            <tr key={b.id} className="border-t border-slate-100 dark:border-slate-800">
              <td className="py-2 pr-2"><div className="font-bold truncate max-w-[160px]">{b.name}</div><div className="text-[10px] text-slate-400">{b.username ? '@' + b.username : ''} · {b.audience} users · <span style={{ color: b.status === 'working' ? '#10b981' : '#94a3b8' }}>{b.status}</span></div></td>
              <td className="truncate max-w-[140px] text-slate-500">{b.owner}</td>
              <td className="font-mono">{b.runs}</td>
              <td className="font-mono"><span style={{ color: SPEED[b.speed][1] }}>{b.avgMs == null ? '—' : `${b.avgMs} ms`}</span> <span className="text-slate-400">/ {b.p95Ms ?? '—'}</span></td>
              <td className="font-mono" style={{ color: b.errorRate >= 20 ? '#ef4444' : undefined }}>{b.errors} ({b.errorRate}%)</td>
              <td><Bar pct={(b.busyMs / maxBusy) * 100} color="linear-gradient(90deg,#6366f1,#ec4899)" /><div className="text-[10px] text-slate-400 mt-0.5">{b.loadShare}% of server time</div></td>
              <td className="text-right whitespace-nowrap">
                <button title={t('why', lang)} className={`${btn} bg-slate-100 dark:bg-slate-800`} onClick={() => why(b)}><Search className="w-3 h-3 inline" /></button>{' '}
                {b.status === 'working'
                  ? <><button title="Restart" className={`${btn} bg-amber-100 text-amber-700`} onClick={() => setAsk({ bot: b, action: 'restart' })}><RotateCw className="w-3 h-3 inline" /></button>{' '}
                    <button title="Stop" className={`${btn} bg-rose-100 text-rose-700`} onClick={() => setAsk({ bot: b, action: 'stop' })}><Square className="w-3 h-3 inline" /></button></>
                  : <button title="Start" className={`${btn} bg-emerald-100 text-emerald-700`} onClick={() => setAsk({ bot: b, action: 'start' })}><Play className="w-3 h-3 inline" /></button>}
              </td>
            </tr>))}</tbody>
        </table>
        {d.bots.length === 0 && <p className="text-xs text-slate-500 py-4">No bots yet.</p>}
      </div>
      {diag && (
        <div className="fixed inset-0 z-90 bg-black/70 flex items-center justify-center p-4" onClick={() => setDiag(null)}>
          <div className="w-full max-w-lg rounded-3xl bg-white dark:bg-slate-900 p-5 space-y-3" onClick={(ev) => ev.stopPropagation()}>
            <div className="font-black text-slate-900 dark:text-white">Why is “{diag.bot.name}” {diag.bot.avgMs ? `at ${diag.bot.avgMs} ms` : 'idle'}?</div>
            {diag.reasons.map((r: any, i: number) => (
              <div key={i} className={`flex gap-2 text-xs p-2.5 rounded-2xl ${r.level === 'bad' ? 'bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-300' : r.level === 'warn' ? 'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-300' : r.level === 'ok' ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300' : 'bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300'}`}>
                {r.level === 'bad' ? <XCircle className="w-4 h-4 shrink-0" /> : r.level === 'ok' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertTriangle className="w-4 h-4 shrink-0" />}<span>{r.text}</span>
              </div>))}
            <button className={`${btn} bg-slate-800 text-white w-full`} onClick={() => setDiag(null)}>Close</button>
          </div>
        </div>)}
      <ConfirmationModal isOpen={!!ask} onClose={() => setAsk(null)} onConfirm={act}
        title={ask ? `${ask.action[0].toUpperCase() + ask.action.slice(1)} “${ask.bot.name}”?` : ''}
        message={ask ? `The owner (${ask.bot.owner}) will be notified. ${ask.action === 'stop' ? 'The bot stops answering users until it is started again.' : ''}` : ''}
        confirmText={ask ? ask.action[0].toUpperCase() + ask.action.slice(1) : ''} isDestructive={ask?.action === 'stop'} />
    </div>
  );
};

// ------------------------------------------------------------------------------------------ DATABASE
export const DatabasePanel: React.FC<{ lang: Lang }> = ({ lang }) => {
  const [d, setD] = useState<any>(null); const [msg, setMsg] = useState(''); const [busy, setBusy] = useState('');
  const [sql, setSql] = useState('SELECT id, email, plan, points FROM users ORDER BY created_at DESC LIMIT 20');
  const [res, setRes] = useState<any>(null); const [sqlErr, setSqlErr] = useState('');
  const load = useCallback(() => apiService.adminGet('database').then(setD).catch((x) => setMsg(errMsg(x))), []);
  useEffect(() => { load(); }, [load]);
  const act = async (action: string, db = 'app') => {
    setBusy(action + db);
    try {
      const r = await apiService.adminPost('database/action', { action, db });
      setMsg(action === 'vacuum' ? `Vacuum done: ${fmtBytes(r.before)} → ${fmtBytes(r.after)}` : action === 'integrity' ? (r.success ? 'Integrity check: OK' : 'Integrity problems: ' + r.result.join('; ')) : action === 'backup' ? `Snapshot saved: ${r.name} (${fmtBytes(r.size)})` : 'Done');
      load();
    } catch (x) { setMsg(errMsg(x)); } finally { setBusy(''); }
  };
  const runSql = async () => { setSqlErr(''); try { setRes(await apiService.adminPost('database/query', { sql, db: 'app' })); } catch (x) { setSqlErr(errMsg(x)); setRes(null); } };
  if (!d) return <p className="text-xs text-slate-500">{msg || 'Loading…'}</p>;
  return (
    <div className="space-y-4">
      {msg && <p className="text-xs font-bold text-blue-600">{msg}</p>}
      {(['app', 'engine'] as const).filter((k) => d[k]).map((k) => (
        <div key={k} className={card + ' space-y-3'}>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 font-black text-sm"><Database className="w-4 h-4 text-indigo-500" />{k === 'app' ? 'Core database' : 'Bot engine database'} <span className="text-[11px] text-slate-400 font-mono">{d[k].path}</span></div>
            <div className="ml-auto flex flex-wrap gap-1.5">
              {[['integrity', 'Integrity check'], ['checkpoint', 'Flush WAL'], ['optimize', 'Optimize'], ['vacuum', 'VACUUM'], ['backup', 'Snapshot backup']].map(([a, l]) => (
                <button key={a} disabled={!!busy} onClick={() => act(a, k)} className={`${btn} bg-gradient-to-r from-indigo-500 to-violet-500 text-white`}>{busy === a + k ? '…' : l}</button>))}
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-center">
            {[['Size', fmtBytes(d[k].size)], ['WAL file', fmtBytes(d[k].wal)], ['Journal', d[k].journal || '—'], ['Fragmentation', `${d[k].fragmentationPct ?? 0}%`], ['Tables', d[k].tables.length]].map(([a, b]) => (
              <div key={a as string} className="rounded-2xl bg-slate-50 dark:bg-slate-800 p-2"><div className="text-[10px] uppercase text-slate-400 font-bold">{a}</div><div className="font-black text-sm">{b}</div></div>))}
          </div>
          <div className="flex flex-wrap gap-1.5">{d[k].tables.map((tb: any) => (<span key={tb.name} className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-[11px] font-mono">{tb.name} <b>{tb.rows ?? '?'}</b></span>))}</div>
        </div>))}
      {d.backups?.length > 0 && <div className={card}><div className="text-xs font-black mb-1">Snapshots (newest 10 kept)</div>{d.backups.map((b: any) => <div key={b.name} className="text-[11px] font-mono text-slate-500">{b.name} · {fmtBytes(b.size)}</div>)}</div>}
      <div className={card + ' space-y-2'}>
        <div className="text-xs font-black flex items-center gap-1.5"><Wrench className="w-4 h-4 text-emerald-500" />{t('sql', lang)} <span className="font-normal text-slate-400">(SELECT only · secret columns are masked)</span></div>
        <textarea value={sql} onChange={(e) => setSql(e.target.value)} rows={3} className="w-full p-3 rounded-2xl font-mono text-xs bg-slate-900 text-emerald-300 border border-slate-700" />
        <button onClick={runSql} className={`${btn} bg-emerald-600 text-white`}>{t('run', lang)}</button>
        {sqlErr && <p className="text-xs text-rose-600 font-bold">{sqlErr}</p>}
        {res && (<div className="overflow-x-auto max-h-80 rounded-2xl border border-slate-200 dark:border-slate-800"><table className="w-full text-[11px] font-mono">
          <thead className="bg-slate-100 dark:bg-slate-800"><tr>{res.columns.map((c: string) => <th key={c} className="text-left px-2 py-1">{c}</th>)}</tr></thead>
          <tbody>{res.rows.map((r: any[], i: number) => <tr key={i} className="border-t border-slate-100 dark:border-slate-800">{r.map((v, j) => <td key={j} className="px-2 py-1 max-w-[260px] truncate">{String(v ?? '')}</td>)}</tr>)}</tbody></table>
          <div className="px-2 py-1 text-[10px] text-slate-400">{res.rows.length} rows · {res.ms} ms{res.truncated ? ' · truncated' : ''}</div></div>)}
      </div>
    </div>
  );
};

// ------------------------------------------------------------------------------------------ LOGS
const LV: Record<string, string> = { INFO: '#60a5fa', WARNING: '#fbbf24', ERROR: '#f87171', CRITICAL: '#fb7185' };
export const LogsPanel: React.FC<{ lang: Lang }> = ({ lang }) => {
  const [lines, setLines] = useState<any[]>([]); const [level, setLevel] = useState('ALL'); const [q, setQ] = useState(''); const [live, setLive] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const load = useCallback(() => apiService.adminGet(`logs?level=${level}&q=${encodeURIComponent(q)}`).then((r) => setLines(r.lines)).catch(() => {}), [level, q]);
  useEffect(() => { load(); if (!live) return; const id = setInterval(load, 2500); return () => clearInterval(id); }, [load, live]);
  useEffect(() => { if (live && box.current) box.current.scrollTop = box.current.scrollHeight; }, [lines, live]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {['ALL', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'].map((l) => <button key={l} onClick={() => setLevel(l)} className={`${btn} ${level === l ? 'bg-indigo-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'}`}>{l}</button>)}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter text / module / bot id" className="flex-1 min-w-[160px] px-3 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700" />
        <button onClick={() => setLive((v) => !v)} className={`${btn} ${live ? 'bg-emerald-600 text-white' : 'bg-slate-200 dark:bg-slate-700'}`}>{live ? '● Live' : 'Paused'}</button>
      </div>
      <div ref={box} className="rounded-3xl bg-slate-950 p-3 h-[460px] overflow-auto font-mono text-[11px] leading-relaxed">
        {lines.length === 0 && <div className="text-slate-500">No log lines yet.</div>}
        {lines.map((l) => (<div key={l.i} className="whitespace-pre-wrap break-all"><span className="text-slate-500">{l.t}</span> <span style={{ color: LV[l.level] || '#94a3b8' }} className="font-bold">{l.level.padEnd(8)}</span> <span className="text-violet-300">{l.src}</span> <span className="text-slate-200">{l.msg}</span></div>))}
      </div>
      <p className="text-[10px] text-slate-400">{t('logs', lang)} · tokens, keys and e-mail addresses are hidden automatically.</p>
    </div>
  );
};

// ------------------------------------------------------------------------------------------ SECURITY
const ST: Record<string, { c: string; i: React.ReactNode }> = {
  ok: { c: '#10b981', i: <CheckCircle2 className="w-4 h-4" /> }, info: { c: '#3b82f6', i: <CheckCircle2 className="w-4 h-4" /> },
  warn: { c: '#f59e0b', i: <AlertTriangle className="w-4 h-4" /> }, bad: { c: '#ef4444', i: <XCircle className="w-4 h-4" /> }, critical: { c: '#be123c', i: <ShieldAlert className="w-4 h-4" /> },
};
export const EventList: React.FC<{ events: any[]; onResolve: (id: string) => void }> = ({ events, onResolve }) => (
  <div className="space-y-2">
    {events.length === 0 && <p className="text-xs text-emerald-600 font-bold">No security events.</p>}
    {events.map((ev) => (
      <div key={ev.id} className={`flex gap-2 p-3 rounded-2xl text-xs border ${ev.resolved ? 'opacity-50' : ''}`} style={{ borderColor: (ST[ev.severity] || ST.info).c + '55', background: (ST[ev.severity] || ST.info).c + '12' }}>
        <span style={{ color: (ST[ev.severity] || ST.info).c }} className="shrink-0 mt-0.5">{(ST[ev.severity] || ST.info).i}</span>
        <div className="min-w-0 flex-1"><div className="font-black text-slate-900 dark:text-white">{ev.title}</div><div className="text-slate-600 dark:text-slate-300 mt-0.5">{ev.detail}</div><div className="text-[10px] text-slate-400 mt-1">{new Date(ev.ts).toLocaleString()} · {ev.kind}</div></div>
        {!ev.resolved && <button className={`${btn} bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 self-start`} onClick={() => onResolve(ev.id)}>Mark handled</button>}
      </div>))}
  </div>
);

export const SecurityPanel: React.FC<{ lang: Lang }> = ({ lang }) => {
  const [d, setD] = useState<any>(null); const [busy, setBusy] = useState(false); const [msg, setMsg] = useState('');
  const load = useCallback(() => apiService.adminGet('security').then(setD).catch((x) => setMsg(errMsg(x))), []);
  useEffect(() => { load(); }, [load]);
  const scan = async (fix?: string) => { setBusy(true); try { setD(await apiService.adminPost('security/scan', fix ? { fix } : {})); setMsg(fix ? 'Fixed and re-checked' : 'Scan finished'); } catch (x) { setMsg(errMsg(x)); } finally { setBusy(false); } };
  if (!d) return <p className="text-xs text-slate-500">{msg || 'Loading…'}</p>;
  const g = d.level === 'ok' ? ['#10b981', '#06b6d4'] : d.level === 'warn' ? ['#f59e0b', '#f97316'] : ['#ef4444', '#be123c'];
  return (
    <div className="space-y-4">
      <div className="rounded-3xl p-5 text-white shadow-lg flex flex-wrap items-center gap-4" style={{ background: `linear-gradient(135deg, ${g[0]}, ${g[1]})` }}>
        {d.level === 'ok' ? <ShieldCheck className="w-14 h-14" /> : <ShieldAlert className="w-14 h-14" />}
        <div><div className="text-xs font-black uppercase tracking-wider opacity-90">{t('score', lang)}</div><div className="text-4xl font-black">{d.score}<span className="text-lg opacity-80">/100</span></div></div>
        <div className="text-xs opacity-95 space-y-0.5">{Object.entries(d.openEvents || {}).map(([k, n]) => <div key={k}>{String(n)} open {k} alert(s) this week</div>)}</div>
        <button disabled={busy} onClick={() => scan()} className={`${btn} bg-white text-slate-900 ml-auto`}>{busy ? 'Scanning…' : t('scan', lang)}</button>
      </div>
      {msg && <p className="text-xs font-bold text-blue-600">{msg}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {d.checks.map((c: any) => (
          <div key={c.id} className={card + ' !p-3 flex gap-2'} style={{ borderColor: (ST[c.status] || ST.ok).c + '66' }}>
            <span style={{ color: (ST[c.status] || ST.ok).c }} className="mt-0.5 shrink-0">{(ST[c.status] || ST.ok).i}</span>
            <div className="min-w-0 flex-1 text-xs"><div className="font-black text-slate-900 dark:text-white">{c.title}</div><div className="text-slate-500 mt-0.5">{c.detail}</div>
              {c.fix && <button className={`${btn} mt-1.5 bg-indigo-600 text-white`} onClick={() => scan(c.fix)}>Fix now</button>}</div>
          </div>))}
      </div>
      {d.secrets?.length > 0 && <div className={card}><div className="text-xs font-black mb-2 text-rose-600">Keys pasted in bot code</div>{d.secrets.map((s: any) => <div key={s.botId} className="text-xs">{s.bot}: {s.items.map((i: any) => `${i.command} (${i.found.join(', ')})`).join('; ')}</div>)}</div>}
      {d.tokens?.length > 0 && <div className={card}><div className="text-xs font-black mb-2">Token health (just checked)</div><div className="flex flex-wrap gap-1.5">{d.tokens.map((x: any) => <span key={x.botId} className="px-2 py-1 rounded-lg text-[11px] font-bold text-white" style={{ background: x.status === 'valid' ? '#10b981' : x.status === 'unreachable' ? '#94a3b8' : '#ef4444' }}>{x.bot}: {x.status}</span>)}</div></div>}
      <div className={card}><div className="text-xs font-black mb-2">{t('alerts', lang)}</div>
        <EventList events={d.events} onResolve={async (id) => { await apiService.adminPut(`security/events/${id}/resolve`, {}); load(); }} /></div>
      <AuditLogCard />
    </div>
  );
};

/** Read-only trail of every admin mutation (who/what/when), plus platform-API-key regenerations. */
const AuditLogCard: React.FC = () => {
  const [rows, setRows] = useState<any[] | null>(null);
  const [msg, setMsg] = useState('');
  useEffect(() => { apiService.adminGet('audit?limit=100').then((r: any) => setRows(r.entries || [])).catch((x) => setMsg(errMsg(x))); }, []);
  return (
    <div className={card}>
      <div className="text-xs font-black mb-2">Admin audit log</div>
      {msg && <p className="text-xs text-rose-600 font-bold">{msg}</p>}
      {!rows ? <p className="text-xs text-slate-500">Loading…</p> : rows.length === 0 ? <p className="text-xs text-slate-500">No admin actions recorded yet.</p> : (
        <div className="max-h-72 overflow-y-auto space-y-1">
          {rows.map((r) => (
            <div key={r.id} className="text-[11px] font-mono flex flex-wrap gap-x-2 gap-y-0.5 border-b border-slate-100 dark:border-slate-800 pb-1">
              <span className="text-slate-400 shrink-0">{(r.at || '').replace('T', ' ').slice(0, 19)}</span>
              <span className="font-black text-slate-900 dark:text-white shrink-0">{r.uid}</span>
              <span className="text-indigo-600 dark:text-indigo-400">{r.action}</span>
              {r.targetId && <span className="text-slate-500">→ {r.targetId}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/** The account owner's own Security Center (Settings → Security). */
export const SecurityCenterCard: React.FC = () => {
  const [d, setD] = useState<any>(null); const [busy, setBusy] = useState(false); const [msg, setMsg] = useState('');
  const load = useCallback(() => apiService.api('GET', '/security').then(setD).catch((x: any) => setMsg(errMsg(x))), []);
  useEffect(() => { load(); }, [load]);
  const scan = async () => { setBusy(true); try { setD(await apiService.api('POST', '/security/scan')); setMsg(''); } catch (x) { setMsg(errMsg(x)); } finally { setBusy(false); } };
  if (!d) return <p className="text-xs text-slate-500">{msg || 'Loading…'}</p>;
  const g = d.level === 'ok' ? ['#10b981', '#06b6d4'] : d.level === 'warn' ? ['#f59e0b', '#f97316'] : ['#ef4444', '#be123c'];
  return (
    <div className="space-y-3" data-testid="security-center">
      <div className="rounded-3xl p-4 text-white flex items-center gap-3 shadow" style={{ background: `linear-gradient(135deg, ${g[0]}, ${g[1]})` }}>
        {d.level === 'ok' ? <ShieldCheck className="w-9 h-9" /> : <ShieldAlert className="w-9 h-9" />}
        <div className="flex-1"><div className="font-black">{d.level === 'ok' ? 'Your account looks safe' : d.level === 'warn' ? 'Needs attention' : 'Action needed now'}</div>
          <div className="text-[11px] opacity-90">Keys in code, bot-token health and sign-ins are watched all the time. You are warned here first, then on Telegram.</div></div>
        <button disabled={busy} onClick={scan} className={`${btn} bg-white text-slate-900`}>{busy ? 'Scanning…' : 'Scan now'}</button>
      </div>
      {msg && <p className="text-xs text-rose-600 font-bold">{msg}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {d.checks.map((c: any) => (
          <div key={c.id} className="flex gap-2 p-3 rounded-2xl border text-xs" style={{ borderColor: (ST[c.status] || ST.ok).c + '66' }}>
            <span style={{ color: (ST[c.status] || ST.ok).c }} className="shrink-0 mt-0.5">{(ST[c.status] || ST.ok).i}</span>
            <div><div className="font-black text-slate-900 dark:text-white">{c.title}</div><div className="text-slate-500">{c.detail}</div></div>
          </div>))}
      </div>
      {d.secrets?.length > 0 && <div className="p-3 rounded-2xl bg-rose-50 dark:bg-rose-950/30 text-xs text-rose-700 dark:text-rose-300">
        <b>Move these to Environment Variables and replace the keys:</b>{d.secrets.map((s: any) => <div key={s.botId}>• {s.bot}: {s.items.map((i: any) => `${i.command} → ${i.found.join(', ')}`).join('; ')}</div>)}</div>}
      <EventList events={d.events} onResolve={async (id) => { await apiService.api('PUT', '/security/events/' + id + '/resolve'); load(); }} />
    </div>
  );
};
