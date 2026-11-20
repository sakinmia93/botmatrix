import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BotAvatar } from './BotAvatar';
import {
  Activity, BarChart3, Users, Globe2, Radio, UserCog, Wrench, RefreshCw, Loader2, Bot as BotIcon,
  AlertTriangle, CheckCircle2, Pause, Play, XCircle, Trash2, ShieldCheck, Terminal, Clock, ExternalLink,
  TrendingUp, UserPlus, UserX, Zap, Timer, Bug, Percent, Eye, Send, Power, Eraser, RotateCcw, UserMinus, Ban, CalendarX,
} from 'lucide-react';
import { BotItem, BotStudioTab, BroadcastItem } from '../types';
import { apiService, apiErrorMessage } from '../services/apiService';
import { ConfirmationModal } from './ConfirmationModal';

interface Props {
  bot: BotItem;
  showToast: (msg: string) => void;
  onGoTab: (t: BotStudioTab) => void;
  onUpdateBot?: (b: BotItem) => void;
  onOpenBroadcast?: (broadcastId: string) => void;
}

type Sub = 'Executions' | 'Users' | 'Broadcasts' | 'Permissions' | 'Maintenance';
// every section has its own accent so the page reads at a glance
const SUBS: { id: Sub; icon: React.ReactNode; grad: string }[] = [
  { id: 'Executions', icon: <Activity className="w-4 h-4" />, grad: 'from-blue-500 to-indigo-600' },
  { id: 'Users', icon: <Users className="w-4 h-4" />, grad: 'from-emerald-500 to-teal-600' },
  { id: 'Broadcasts', icon: <Radio className="w-4 h-4" />, grad: 'from-fuchsia-500 to-pink-600' },
  { id: 'Permissions', icon: <UserCog className="w-4 h-4" />, grad: 'from-amber-500 to-orange-600' },
  { id: 'Maintenance', icon: <Wrench className="w-4 h-4" />, grad: 'from-rose-500 to-red-600' },
];

const RANGES = [{ d: 1, l: '24h' }, { d: 7, l: '7d' }, { d: 30, l: '30d' }];
const nf = (n: number) => (n ?? 0).toLocaleString();
const PALETTE = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#ec4899', '#84cc16'];

const TONES: Record<string, { card: string; chip: string; text: string }> = {
  blue: { card: 'from-blue-500/15 via-blue-500/5 to-transparent border-blue-500/30', chip: 'bg-blue-500 text-white shadow-blue-500/30', text: 'text-blue-600 dark:text-blue-300' },
  emerald: { card: 'from-emerald-500/15 via-emerald-500/5 to-transparent border-emerald-500/30', chip: 'bg-emerald-500 text-white shadow-emerald-500/30', text: 'text-emerald-600 dark:text-emerald-300' },
  violet: { card: 'from-violet-500/15 via-violet-500/5 to-transparent border-violet-500/30', chip: 'bg-violet-500 text-white shadow-violet-500/30', text: 'text-violet-600 dark:text-violet-300' },
  amber: { card: 'from-amber-500/15 via-amber-500/5 to-transparent border-amber-500/30', chip: 'bg-amber-500 text-white shadow-amber-500/30', text: 'text-amber-600 dark:text-amber-300' },
  rose: { card: 'from-rose-500/15 via-rose-500/5 to-transparent border-rose-500/30', chip: 'bg-rose-500 text-white shadow-rose-500/30', text: 'text-rose-600 dark:text-rose-300' },
  cyan: { card: 'from-cyan-500/15 via-cyan-500/5 to-transparent border-cyan-500/30', chip: 'bg-cyan-500 text-white shadow-cyan-500/30', text: 'text-cyan-600 dark:text-cyan-300' },
  pink: { card: 'from-pink-500/15 via-pink-500/5 to-transparent border-pink-500/30', chip: 'bg-pink-500 text-white shadow-pink-500/30', text: 'text-pink-600 dark:text-pink-300' },
  slate: { card: 'from-slate-500/15 via-slate-500/5 to-transparent border-slate-500/30', chip: 'bg-slate-500 text-white shadow-slate-500/30', text: 'text-slate-600 dark:text-slate-300' },
};

const Stat: React.FC<{ label: string; value: React.ReactNode; hint?: string; tone?: keyof typeof TONES; icon?: React.ReactNode }> = ({ label, value, hint, tone = 'blue', icon }) => {
  const t = TONES[tone];
  return (
    <div className={`relative overflow-hidden p-4 rounded-2xl border bg-gradient-to-br ${t.card} backdrop-blur-sm hover:-translate-y-0.5 hover:shadow-lg transition-all`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</div>
          <div className={`text-3xl font-black mt-1 tabular-nums ${t.text}`}>{value}</div>
          {hint && <div className="text-[10px] font-semibold text-slate-500 mt-0.5">{hint}</div>}
        </div>
        {icon && <div className={`w-9 h-9 shrink-0 rounded-xl flex items-center justify-center shadow-md ${t.chip}`}>{icon}</div>}
      </div>
    </div>
  );
};

const Panel: React.FC<{ title: string; icon: React.ReactNode; grad: string; right?: React.ReactNode; children: React.ReactNode }> = ({ title, icon, grad, right, children }) => (
  <div className="glass-panel rounded-3xl overflow-hidden border border-slate-200 dark:border-slate-800 shadow-sm">
    <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-slate-200/70 dark:border-slate-800/70 bg-gradient-to-r from-slate-50 to-transparent dark:from-slate-900/60">
      <div className="flex items-center gap-2.5 min-w-0">
        <span className={`w-8 h-8 rounded-xl bg-gradient-to-br ${grad} text-white flex items-center justify-center shadow-md shrink-0`}>{icon}</span>
        <h3 className="text-sm font-extrabold text-slate-900 dark:text-white truncate">{title}</h3>
      </div>
      {right}
    </div>
    <div className="p-5">{children}</div>
  </div>
);

const Chart: React.FC<{
  labels: string[];
  series: { name: string; color: string; values: number[]; line?: boolean }[];
}> = ({ labels, series }) => {
  const W = 720, H = 220, P = { l: 36, r: 8, t: 10, b: 24 };
  const n = Math.max(labels.length, 1);
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const niceMax = Math.ceil(max / 4) * 4 || 4;
  const iw = W - P.l - P.r, ih = H - P.t - P.b;
  const bars = series.filter((s) => !s.line);
  const slot = iw / n;
  const bw = Math.max(2, Math.min(28, (slot * 0.7) / Math.max(bars.length, 1)));
  const x = (i: number) => P.l + slot * i + slot / 2;
  const y = (v: number) => P.t + ih - (v / niceMax) * ih;
  const step = Math.ceil(n / 10);
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img">
        {[0, 1, 2, 3, 4].map((g) => {
          const v = (niceMax / 4) * g;
          return (
            <g key={g}>
              <line x1={P.l} x2={W - P.r} y1={y(v)} y2={y(v)} className="stroke-slate-200 dark:stroke-slate-800" strokeWidth={1} />
              <text x={P.l - 6} y={y(v) + 3} textAnchor="end" className="fill-slate-400" fontSize={9}>{Math.round(v)}</text>
            </g>
          );
        })}
        {labels.map((l, i) => (
          <g key={i}>
            <rect x={P.l + slot * i} y={P.t} width={slot} height={ih} fill="transparent" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
            {i % step === 0 && <text x={x(i)} y={H - 8} textAnchor="middle" className="fill-slate-400" fontSize={9}>{l}</text>}
          </g>
        ))}
        {bars.map((s, si) =>
          s.values.map((v, i) => {
            const off = (si - (bars.length - 1) / 2) * bw;
            const h = ih - (y(v) - P.t);
            return <rect key={`${si}-${i}`} x={x(i) + off - bw / 2} y={y(v)} width={bw} height={Math.max(h, 0)} rx={2} fill={s.color} opacity={hover === null || hover === i ? 1 : 0.5} pointerEvents="none" />;
          }),
        )}
        {series.filter((s) => s.line).map((s, si) => (
          <g key={`l${si}`} pointerEvents="none">
            <polyline fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')} />
            {s.values.map((v, i) => <circle key={i} cx={x(i)} cy={y(v)} r={2.5} fill={s.color} />)}
          </g>
        ))}
      </svg>
      {hover !== null && (
        <div className="absolute top-1 right-2 text-[10px] bg-slate-900 text-white rounded-lg px-2.5 py-1.5 shadow-lg pointer-events-none">
          <div className="font-bold">{labels[hover]}</div>
          {series.map((s) => (
            <div key={s.name} className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-sm" style={{ background: s.color }} /> {s.name}: <b>{nf(s.values[hover])}</b>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-3 mt-1 justify-center">
        {series.map((s) => (
          <span key={s.name} className="flex items-center gap-1.5 text-[10px] text-slate-500">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} /> {s.name}
          </span>
        ))}
      </div>
    </div>
  );
};

const Bar: React.FC<{ percent: number; hex?: string; grad?: string; h?: string }> = ({ percent, hex, grad = 'from-blue-500 to-indigo-500', h = 'h-2.5' }) => (
  <div className={`${h} rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden`}>
    <div className={`h-full rounded-full transition-all duration-700 ${hex ? '' : 'bg-gradient-to-r ' + grad}`}
      style={{ background: hex ? `linear-gradient(90deg, ${hex}, ${hex}cc)` : undefined, width: `${Math.min(100, Math.max(percent > 0 ? 2 : 0, percent))}%` }} />
  </div>
);

const Empty: React.FC<{ text: string; icon?: React.ReactNode }> = ({ text, icon }) => (
  <div className="py-10 flex flex-col items-center gap-2 text-center text-xs text-slate-500">
    <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-400">{icon || <BarChart3 className="w-6 h-6" />}</div>
    {text}
  </div>
);

const BC_TONE: Record<string, { stripe: string; pill: string; bar: string }> = {
  Active: { stripe: 'bg-emerald-500', pill: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300', bar: 'from-emerald-500 to-teal-500' },
  Paused: { stripe: 'bg-amber-500', pill: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300', bar: 'from-amber-500 to-orange-500' },
  Done: { stripe: 'bg-blue-500', pill: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300', bar: 'from-blue-500 to-indigo-500' },
  Completed: { stripe: 'bg-blue-500', pill: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300', bar: 'from-blue-500 to-indigo-500' },
  Cancelled: { stripe: 'bg-slate-400', pill: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300', bar: 'from-slate-400 to-slate-500' },
  Failed: { stripe: 'bg-rose-500', pill: 'bg-rose-100 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300', bar: 'from-rose-500 to-red-500' },
};

export const BotAdminView: React.FC<Props> = ({ bot, showToast, onGoTab, onOpenBroadcast }) => {
  const [sub, setSub] = useState<Sub>('Executions');
  const [days, setDays] = useState(7);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [cmdQ, setCmdQ] = useState('');

  const [maintOn, setMaintOn] = useState(false);
  const [maintMsg, setMaintMsg] = useState('');
  const [busy, setBusy] = useState('');
  const [confirm, setConfirm] = useState<{ title: string; message: string; confirmText: string; destructive: boolean; run: () => void } | null>(null);
  const ask = (title: string, message: string, run: () => void, destructive = true, confirmText = 'Confirm') => setConfirm({ title, message, confirmText, destructive, run });

  const [bcs, setBcs] = useState<BroadcastItem[]>([]);
  const [admins, setAdmins] = useState<string[]>([]);
  const [adminInput, setAdminInput] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    try {
      const d = await apiService.getBotAdminOverview(bot.id, days);
      setData(d);
      setMaintOn(!!d.maintenance?.on);
      setMaintMsg((m) => m || d.maintenance?.message || '');
    } catch (e) {
      setErr(apiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [bot.id, days]);

  useEffect(() => { load(); }, [load]);

  const loadBroadcasts = useCallback(async () => {
    try {
      const all = await apiService.getBroadcasts();
      setBcs(all.filter((b) => (b.targetBotIds || []).includes(bot.id)));
    } catch (e) { showToast(apiErrorMessage(e)); }
  }, [bot.id, showToast]);

  useEffect(() => { if (sub === 'Broadcasts') loadBroadcasts(); }, [sub, loadBroadcasts]);
  useEffect(() => { if (sub === 'Permissions') apiService.getGlobalAdmins().then(setAdmins).catch(() => {}); }, [sub]);

  const ex = data?.executions;
  const us = data?.users;

  const cmds = useMemo(() => {
    const q = cmdQ.trim().toLowerCase();
    return ((ex?.commands as any[]) || []).filter((c) => !q || String(c.name).toLowerCase().includes(q));
  }, [ex, cmdQ]);

  const act = async (action: string) => {
    setBusy(action);
    try {
      const r = await apiService.botAdminAction(bot.id, action);
      showToast(r.message || 'Done.');
      await load();
    } catch (e) { showToast(apiErrorMessage(e)); }
    finally { setBusy(''); }
  };

  const saveMaint = async (on: boolean) => {
    setBusy('maint');
    try {
      const r = await apiService.setBotMaintenance(bot.id, on, maintMsg);
      setMaintOn(!!r.on);
      showToast(r.on ? 'Maintenance mode is ON — only admins can use the bot.' : 'Maintenance mode is OFF — bot is live.');
      await load();
    } catch (e) { showToast(apiErrorMessage(e)); }
    finally { setBusy(''); }
  };

  const bcAct = async (id: string, kind: 'pause' | 'resume' | 'cancel') => {
    try {
      if (kind === 'pause') await apiService.pauseBroadcast(id);
      else if (kind === 'resume') await apiService.resumeBroadcast(id);
      else await apiService.cancelBroadcast(id);
      await loadBroadcasts();
    } catch (e) { showToast(apiErrorMessage(e)); }
  };

  const addAdmin = async () => {
    const v = adminInput.trim();
    if (!v) return;
    try { setAdmins(await apiService.addGlobalAdmin(v)); setAdminInput(''); showToast('Admin added.'); }
    catch (er) { showToast(apiErrorMessage(er)); }
  };
  const rmAdmin = async (id: string) => {
    try { setAdmins(await apiService.removeGlobalAdmin(id)); showToast('Admin removed.'); }
    catch (er) { showToast(apiErrorMessage(er)); }
  };

  const topLang = us?.languages?.[0];

  const subMeta = SUBS.find((s) => s.id === sub)!;
  const botHandle = bot.username ? '@' + String(bot.username).replace(/^@/, '') : '';
  const OPS = [
    { id: 'restart', t: 'Restart bot', d: 'Stop and start the bot runtime.', c: 'Restart the bot now? It is offline for a moment.', icon: <Power className="w-4 h-4" />, tone: 'blue', danger: false },
    { id: 'clear-errors', t: 'Clear error log', d: 'Delete all recorded runtime errors.', c: 'Clear the error log? This cannot be undone.', icon: <Eraser className="w-4 h-4" />, tone: 'amber', danger: true },
    { id: 'reset-stats', t: 'Reset execution stats', d: 'Wipe command counters and the charts.', c: 'Reset all execution statistics for this bot? This cannot be undone.', icon: <RotateCcw className="w-4 h-4" />, tone: 'violet', danger: true },
    { id: 'remove-left-users', t: 'Remove users who left', d: 'Delete chat records of users who blocked the bot.', c: 'Remove every user who blocked the bot? This cannot be undone.', icon: <UserMinus className="w-4 h-4" />, tone: 'rose', danger: true },
    { id: 'stop-broadcasts', t: 'Stop all broadcasts', d: 'Cancel running or paused broadcasts of this bot.', c: 'Cancel all running broadcasts for this bot? Unsent messages will not be delivered.', icon: <Ban className="w-4 h-4" />, tone: 'pink', danger: true },
    { id: 'clear-schedules', t: 'Clear scheduled commands', d: 'Cancel every pending runCommandAfter task.', c: 'Cancel all scheduled commands of this bot?', icon: <CalendarX className="w-4 h-4" />, tone: 'cyan', danger: true },
  ];

  return (
    <div className="space-y-5">
      {/* HERO */}
      <div className="relative overflow-hidden rounded-3xl p-5 sm:p-6 text-white bg-gradient-to-br from-blue-600 via-indigo-600 to-violet-700 shadow-xl shadow-indigo-500/20">
        <div className="absolute -top-16 -right-10 w-64 h-64 rounded-full bg-white/10 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-20 left-10 w-56 h-56 rounded-full bg-fuchsia-400/20 blur-3xl pointer-events-none" />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            <BotAvatar src={bot.photoUrl} alt={bot.name} className="w-14 h-14 rounded-2xl ring-2 ring-white/40 shrink-0" iconClassName="w-7 h-7" />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-black tracking-tight truncate">Admin</h2>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${bot.status === 'working' ? 'bg-emerald-400/90 text-emerald-950' : 'bg-white/25 text-white'}`}>{bot.status === 'working' ? 'Online' : 'Stopped'}</span>
                {maintOn && <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-300 text-amber-950 animate-pulse">Maintenance</span>}
              </div>
              <p className="text-xs text-white/80 truncate">{bot.name}{botHandle ? ` · ${botHandle}` : ''} — analytics &amp; full control</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {(sub === 'Executions' || sub === 'Users') && (
              <div className="flex rounded-xl bg-white/15 backdrop-blur p-0.5">
                {RANGES.map((r) => (
                  <button key={r.d} onClick={() => setDays(r.d)} className={`px-3 py-1.5 rounded-lg text-xs font-extrabold transition ${days === r.d ? 'bg-white text-indigo-700 shadow' : 'text-white/80 hover:bg-white/10'}`}>{r.l}</button>
                ))}
              </div>
            )}
            <button onClick={load} className="p-2.5 rounded-xl bg-white/15 hover:bg-white/25 backdrop-blur transition" title="Refresh">
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap gap-2">
          {SUBS.map((s) => (
            <button key={s.id} onClick={() => setSub(s.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-extrabold transition ${sub === s.id ? `bg-white text-slate-900 shadow-lg` : 'bg-white/10 text-white/90 hover:bg-white/20'}`}>
              <span className={`w-6 h-6 rounded-lg bg-gradient-to-br ${s.grad} text-white flex items-center justify-center`}>{React.cloneElement(s.icon as React.ReactElement<any>, { className: 'w-3.5 h-3.5' })}</span>
              {s.id}
            </button>
          ))}
        </div>
      </div>

      {err && (
        <div className="p-4 rounded-2xl bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {err}
        </div>
      )}

      {/* EXECUTIONS */}
      {sub === 'Executions' && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Stat label="Total executions" value={loading && !ex ? '…' : nf(ex?.total)} hint={`last ${days === 1 ? '24 hours' : days + ' days'}`} tone="blue" icon={<Zap className="w-4 h-4" />} />
            <Stat label="Errors" value={nf(ex?.errors)} tone={ex?.errors ? 'rose' : 'emerald'} icon={<Bug className="w-4 h-4" />} hint={ex?.errors ? 'see the Errors tab' : 'all clear'} />
            <Stat label="Error rate" value={`${ex?.errorRate ?? 0}%`} tone="amber" icon={<Percent className="w-4 h-4" />} />
            <Stat label="Avg runtime" value={`${ex?.avgMs ?? 0} ms`} tone="violet" icon={<Timer className="w-4 h-4" />} />
          </div>

          <Panel title="Executions over time" icon={<BarChart3 className="w-4 h-4" />} grad="from-blue-500 to-indigo-600">
            {ex?.series?.length ? (
              <Chart
                labels={ex.series.map((s: any) => s.label)}
                series={[
                  { name: 'Commands', color: '#6366f1', values: ex.series.map((s: any) => s.commands) },
                  { name: 'Errors', color: '#f43f5e', values: ex.series.map((s: any) => s.errors) },
                ]}
              />
            ) : <Empty text="No executions in this period yet." />}
          </Panel>

          <Panel title="All commands" icon={<Terminal className="w-4 h-4" />} grad="from-violet-500 to-purple-600"
            right={<div className="flex items-center gap-2"><span className="text-[10px] font-bold text-slate-500">{cmds.length} listed</span>
              <input value={cmdQ} onChange={(e) => setCmdQ(e.target.value)} placeholder="Filter…" className="px-3 py-1.5 rounded-xl text-xs border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/60 outline-none focus:border-violet-500 w-32 sm:w-44" /></div>}>
            {cmds.length ? (
              <div className="space-y-2.5">
                {cmds.map((c: any, i: number) => {
                  const col = PALETTE[i % PALETTE.length];
                  return (
                    <div key={c.name} className="p-3 rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white/50 dark:bg-slate-900/30 hover:border-violet-400/60 transition grid grid-cols-12 gap-3 items-center">
                      <div className="col-span-12 sm:col-span-4 flex items-center gap-3 min-w-0">
                        <span className="w-8 h-8 rounded-xl text-white text-xs font-black flex items-center justify-center shrink-0 shadow" style={{ background: `linear-gradient(135deg, ${col}, ${col}aa)` }}>{i + 1}</span>
                        <div className="min-w-0">
                          <div className="font-mono text-xs font-bold text-slate-900 dark:text-white truncate">{c.name}</div>
                          <div className="text-[10px] text-slate-500 truncate">{c.defined === false ? 'not defined' : c.lastRun ? `last run ${new Date(c.lastRun).toLocaleString()}` : 'never run'}</div>
                        </div>
                      </div>
                      <div className="col-span-8 sm:col-span-5"><Bar percent={c.percent} hex={col} /></div>
                      <div className="col-span-4 sm:col-span-3 text-right">
                        <div className="text-sm font-black tabular-nums text-slate-900 dark:text-white">{nf(c.runs)} <span className="text-[10px] font-bold text-slate-500">runs</span></div>
                        <div className="text-[10px] text-slate-500">{c.share}% · {c.avgMs} ms{c.errors ? <span className="text-rose-600 font-bold"> · {c.errors} err</span> : null}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : <Empty text="No commands to show." icon={<Terminal className="w-6 h-6" />} />}
          </Panel>
        </div>
      )}

      {/* USERS */}
      {sub === 'Users' && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Total users" value={nf(us?.total)} tone="blue" icon={<Users className="w-4 h-4" />} />
            <Stat label="Active (24h)" value={nf(us?.active24h)} tone="emerald" icon={<Activity className="w-4 h-4" />} />
            <Stat label="Active (7d)" value={nf(us?.active7d)} tone="cyan" icon={<TrendingUp className="w-4 h-4" />} />
            <Stat label="Active (30d)" value={nf(us?.active30d)} tone="violet" icon={<TrendingUp className="w-4 h-4" />} />
            <Stat label="New (24h)" value={nf(us?.new24h)} hint="joined today" tone="pink" icon={<UserPlus className="w-4 h-4" />} />
            <Stat label="New (7d)" value={nf(us?.new7d)} tone="amber" icon={<UserPlus className="w-4 h-4" />} />
            <Stat label="New (30d)" value={nf(us?.new30d)} tone="slate" icon={<UserPlus className="w-4 h-4" />} />
            <Stat label="Blocked" value={nf(us?.blocked)} hint={us?.left ? `${us.left} left the bot` : undefined} tone="rose" icon={<UserX className="w-4 h-4" />} />
          </div>

          <Panel title="New & active users" icon={<BarChart3 className="w-4 h-4" />} grad="from-emerald-500 to-teal-600">
            {us?.growth?.length ? (
              <Chart
                labels={us.growth.map((g: any) => g.label)}
                series={[
                  { name: 'New users', color: '#ec4899', values: us.growth.map((g: any) => g.new) },
                  { name: 'Active users', color: '#10b981', values: us.growth.map((g: any) => g.active), line: true },
                ]}
              />
            ) : <Empty text="No user activity yet." />}
          </Panel>

          <Panel title="User language / country" icon={<Globe2 className="w-4 h-4" />} grad="from-cyan-500 to-blue-600"
            right={topLang ? <span className="text-[11px] text-slate-500">Top: <b className="text-slate-900 dark:text-white">{topLang.name}</b> ({topLang.percent}%)</span> : undefined}>
            {us?.languages?.length ? (
              <>
                <div className="flex h-4 rounded-full overflow-hidden mb-5 shadow-inner bg-slate-100 dark:bg-slate-800">
                  {us.languages.slice(0, 8).map((l: any, i: number) => (
                    <div key={l.code} title={`${l.name} ${l.percent}%`} style={{ width: `${l.percent}%`, background: PALETTE[i] }} className="hover:brightness-110 transition" />
                  ))}
                </div>
                <div className="grid md:grid-cols-2 gap-3">
                  {us.languages.map((l: any, i: number) => {
                    const col = i < 8 ? PALETTE[i] : '#94a3b8';
                    return (
                      <div key={l.code} className="p-3 rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white/50 dark:bg-slate-900/30">
                        <div className="flex items-center justify-between text-xs mb-2">
                          <span className="flex items-center gap-2 min-w-0">
                            <span className="font-mono text-[10px] font-black px-1.5 py-0.5 rounded-md text-white uppercase" style={{ background: col }}>{l.code}</span>
                            <span className="font-bold text-slate-800 dark:text-slate-200 truncate">{l.name}</span>
                          </span>
                          <span className="text-slate-500 shrink-0"><b className="text-slate-900 dark:text-white tabular-nums">{nf(l.users)}</b> · {l.percent}%</span>
                        </div>
                        <Bar percent={l.percent} hex={col} h="h-2" />
                      </div>
                    );
                  })}
                </div>
              </>
            ) : <Empty text="No language data yet — it's collected from users' Telegram language_code." icon={<Globe2 className="w-6 h-6" />} />}
          </Panel>
        </div>
      )}

      {/* BROADCASTS */}
      {sub === 'Broadcasts' && (
        <Panel title="Broadcasts of this bot" icon={<Radio className="w-4 h-4" />} grad="from-fuchsia-500 to-pink-600"
          right={<span className="text-[10px] font-bold text-slate-500">{bcs.length} total</span>}>
          {bcs.length === 0 ? <Empty text="No broadcasts have targeted this bot yet." icon={<Send className="w-6 h-6" />} /> : (
            <div className="space-y-3">
              {bcs.map((b) => {
                const tone = BC_TONE[b.status] || BC_TONE.Cancelled;
                const running = b.status === 'Active' || b.status === 'Paused';
                const pct = b.percent ?? (b.totalTargetUsers ? Math.min(100, Math.round((b.sentCount / b.totalTargetUsers) * 100)) : 0);
                const others = (b.targetBotUsernames || []).filter((u) => u && u.replace(/^@/, '') !== String(bot.username || '').replace(/^@/, ''));
                return (
                  <div key={b.id} className="relative flex rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/40 hover:shadow-lg hover:border-fuchsia-400/50 transition">
                    <div className={`w-1.5 shrink-0 ${tone.stripe}`} />
                    <div className="flex-1 min-w-0 p-4 space-y-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <BotAvatar src={bot.photoUrl} alt={bot.name} className="w-11 h-11 rounded-2xl shrink-0 shadow-md" iconClassName="w-5 h-5" />
                          <div className="min-w-0">
                            <div className="text-sm font-extrabold text-slate-900 dark:text-white truncate">{b.title || b.id}</div>
                            <div className="text-[11px] text-slate-500 truncate"><span className="font-mono text-blue-600 dark:text-blue-400">{botHandle || bot.name}</span> · {b.messageType}{others.length ? ` · +${others.length} more bot${others.length > 1 ? 's' : ''}` : ''}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-wider ${tone.pill}`}>{b.status}</span>
                          <button onClick={() => onOpenBroadcast && onOpenBroadcast(b.id)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-extrabold text-white bg-gradient-to-r from-fuchsia-500 to-pink-600 shadow-md shadow-pink-500/20 hover:brightness-110 transition">
                            <Eye className="w-3.5 h-3.5" /> View details
                          </button>
                        </div>
                      </div>

                      {b.messageText && !['Location','Venue','Contact','Poll','Dice','Forward'].includes(b.messageType) && <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 bg-slate-50 dark:bg-slate-900/60 rounded-xl px-3 py-2 border border-slate-100 dark:border-slate-800">{b.messageText}</p>}

                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="rounded-xl bg-blue-50 dark:bg-blue-950/30 py-2"><div className="text-[9px] font-black uppercase text-blue-500">Target</div><div className="text-sm font-black tabular-nums text-blue-700 dark:text-blue-300">{nf(b.totalTargetUsers)}</div></div>
                        <div className="rounded-xl bg-emerald-50 dark:bg-emerald-950/30 py-2"><div className="text-[9px] font-black uppercase text-emerald-500">Sent</div><div className="text-sm font-black tabular-nums text-emerald-700 dark:text-emerald-300">{nf(b.sentCount)}</div></div>
                        <div className="rounded-xl bg-rose-50 dark:bg-rose-950/30 py-2"><div className="text-[9px] font-black uppercase text-rose-500">Failed</div><div className="text-sm font-black tabular-nums text-rose-700 dark:text-rose-300">{nf(b.failedCount || 0)}</div></div>
                      </div>

                      <div className="flex items-center gap-3">
                        <div className="flex-1"><Bar percent={pct} grad={tone.bar} /></div>
                        <span className="text-xs font-black tabular-nums text-slate-700 dark:text-slate-200 w-10 text-right">{pct}%</span>
                        {running && (
                          <div className="flex gap-1.5 shrink-0">
                            {b.status === 'Active'
                              ? <button onClick={() => ask('Pause broadcast', `Pause “${b.title || b.id}”?`, () => bcAct(b.id, 'pause'), false, 'Pause')} className="p-1.5 rounded-lg bg-amber-100 text-amber-700 hover:bg-amber-200" title="Pause"><Pause className="w-3.5 h-3.5" /></button>
                              : <button onClick={() => ask('Resume broadcast', `Resume “${b.title || b.id}”?`, () => bcAct(b.id, 'resume'), false, 'Resume')} className="p-1.5 rounded-lg bg-emerald-100 text-emerald-700 hover:bg-emerald-200" title="Resume"><Play className="w-3.5 h-3.5" /></button>}
                            <button onClick={() => ask('Cancel broadcast', `Cancel “${b.title || b.id}”? Messages not yet sent will never be delivered.`, () => bcAct(b.id, 'cancel'), true, 'Cancel broadcast')} className="p-1.5 rounded-lg bg-rose-100 text-rose-700 hover:bg-rose-200" title="Cancel"><XCircle className="w-3.5 h-3.5" /></button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      )}

      {/* PERMISSIONS */}
      {sub === 'Permissions' && (
        <Panel title="Bot admins" icon={<UserCog className="w-4 h-4" />} grad="from-amber-500 to-orange-600" right={<span className="text-[10px] font-bold text-slate-500">{admins.length} admin{admins.length === 1 ? '' : 's'}</span>}>
          <p className="text-xs text-slate-500 mb-4">Telegram IDs here are admins on all your bots: they can use bots in maintenance mode and run admin-only commands.</p>
          <form onSubmit={(e) => { e.preventDefault(); const v = adminInput.trim(); if (v) ask('Add bot admin', `Give Telegram ID ${v} admin rights on all your bots?`, () => addAdmin(), false, 'Add admin'); }} className="flex gap-2 mb-4">
            <input value={adminInput} onChange={(e) => setAdminInput(e.target.value)} inputMode="numeric" placeholder="Telegram user ID"
              className="flex-1 px-3.5 py-2.5 rounded-xl text-xs border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/60 outline-none focus:border-amber-500" />
            <button className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 text-white text-xs font-extrabold shadow-md shadow-orange-500/20 hover:brightness-110">Add</button>
          </form>
          {admins.length === 0 ? <Empty text="No admins yet." icon={<UserCog className="w-6 h-6" />} /> : (
            <div className="grid sm:grid-cols-2 gap-2.5">
              {admins.map((a, i) => (
                <div key={a} className="flex items-center justify-between p-3 rounded-2xl border border-amber-500/20 bg-gradient-to-r from-amber-500/10 to-transparent">
                  <span className="flex items-center gap-2.5">
                    <span className="w-8 h-8 rounded-xl text-white text-xs font-black flex items-center justify-center" style={{ background: PALETTE[i % PALETTE.length] }}><ShieldCheck className="w-4 h-4" /></span>
                    <span className="font-mono text-xs font-bold">{a}</span>
                  </span>
                  <button onClick={() => ask('Remove bot admin', `Remove ${a} from bot admins?`, () => rmAdmin(a), true, 'Remove')} className="text-rose-600 p-1.5 hover:bg-rose-100 dark:hover:bg-rose-950/30 rounded-lg" title="Remove"><Trash2 className="w-3.5 h-3.5" /></button>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {/* MAINTENANCE */}
      {sub === 'Maintenance' && (
        <div className="space-y-5">
          <div className={`relative overflow-hidden rounded-3xl p-5 border-2 transition ${maintOn ? 'border-amber-400 bg-gradient-to-br from-amber-100/70 to-orange-100/40 dark:from-amber-950/40 dark:to-orange-950/20' : 'border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 to-transparent'}`}>
            <div className="flex items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-3">
                <span className={`w-11 h-11 rounded-2xl flex items-center justify-center text-white shadow-lg ${maintOn ? 'bg-gradient-to-br from-amber-500 to-orange-600' : 'bg-gradient-to-br from-emerald-500 to-teal-600'}`}><Wrench className="w-5 h-5" /></span>
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900 dark:text-white">Maintenance mode</h3>
                  <p className="text-xs text-slate-600 dark:text-slate-400 max-w-xl">While on, normal users get the message below and no command runs. Bot admins keep full access — handy while you develop.</p>
                </div>
              </div>
              <span className={`px-3 py-1 rounded-full text-[10px] font-black ${maintOn ? 'bg-amber-500 text-white animate-pulse' : 'bg-emerald-500 text-white'}`}>{maintOn ? 'ON' : 'OFF'}</span>
            </div>
            <textarea value={maintMsg} onChange={(e) => setMaintMsg(e.target.value)} rows={3} maxLength={1000}
              placeholder="🛠 The bot is under maintenance. Please try again later."
              className="w-full px-3.5 py-2.5 rounded-xl text-xs border border-slate-200 dark:border-slate-700 bg-white/70 dark:bg-slate-900/60 outline-none focus:border-amber-500" />
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <button disabled={busy === 'maint'} onClick={() => ask(maintOn ? 'Go live' : 'Enable maintenance mode', maintOn ? 'Turn maintenance off? All users will be able to use the bot again.' : 'Turn maintenance on? Normal users will only see your notice and no command will run for them.', () => saveMaint(!maintOn), !maintOn, maintOn ? 'Go live' : 'Enable')}
                className={`px-5 py-2.5 rounded-xl text-xs font-extrabold text-white shadow-md ${maintOn ? 'bg-gradient-to-r from-emerald-500 to-teal-600' : 'bg-gradient-to-r from-amber-500 to-orange-600'} disabled:opacity-50 hover:brightness-110`}>
                {busy === 'maint' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : maintOn ? 'Turn off — go live' : 'Turn on maintenance'}
              </button>
              {maintOn && (
                <button disabled={busy === 'maint'} onClick={() => ask('Update maintenance message', 'Save the new maintenance message? Users see it immediately.', () => saveMaint(true), false, 'Save')} className="px-5 py-2.5 rounded-xl text-xs font-extrabold border border-slate-300 dark:border-slate-700 bg-white/60 dark:bg-slate-900/40">Update message</button>
              )}
              {data?.maintenance?.since && maintOn && (
                <span className="text-[10px] text-slate-500 flex items-center gap-1"><Clock className="w-3 h-3" /> since {new Date(data.maintenance.since).toLocaleString()}</span>
              )}
            </div>
          </div>

          <Panel title="Operations" icon={<CheckCircle2 className="w-4 h-4" />} grad="from-rose-500 to-red-600">
            <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {OPS.map((a) => {
                const t = TONES[a.tone];
                return (
                  <button key={a.id} disabled={!!busy} onClick={() => ask(a.t, a.c, () => act(a.id), a.danger, a.t)}
                    className={`text-left p-4 rounded-2xl border bg-gradient-to-br ${t.card} hover:-translate-y-0.5 hover:shadow-lg transition disabled:opacity-50`}>
                    <div className="flex items-center gap-3">
                      <span className={`w-9 h-9 rounded-xl flex items-center justify-center shadow-md shrink-0 ${t.chip}`}>{busy === a.id ? <Loader2 className="w-4 h-4 animate-spin" /> : a.icon}</span>
                      <div className="min-w-0">
                        <div className="text-xs font-extrabold text-slate-900 dark:text-white">{a.t}</div>
                        <div className="text-[11px] text-slate-500 leading-snug">{a.d}</div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </Panel>

          <Panel title="Manage every part of the bot" icon={<ExternalLink className="w-4 h-4" />} grad="from-indigo-500 to-violet-600">
            <div className="flex flex-wrap gap-2">
              {(['Commands', 'Errors', 'Manage', 'Chats', 'Database', 'Settings'] as BotStudioTab[]).map((t, i) => (
                <button key={t} onClick={() => onGoTab(t)} className="px-4 py-2 rounded-xl text-xs font-extrabold text-white shadow-md hover:brightness-110 hover:-translate-y-0.5 transition flex items-center gap-1.5" style={{ background: `linear-gradient(135deg, ${PALETTE[i]}, ${PALETTE[(i + 3) % PALETTE.length]})` }}>
                  {t} <ExternalLink className="w-3 h-3" />
                </button>
              ))}
            </div>
          </Panel>
        </div>
      )}

      <ConfirmationModal
        isOpen={!!confirm}
        onClose={() => setConfirm(null)}
        onConfirm={() => { const c = confirm; setConfirm(null); c?.run(); }}
        title={confirm?.title || ''}
        message={confirm?.message || ''}
        confirmText={confirm?.confirmText}
        isDestructive={confirm?.destructive}
      />
    </div>
  );
};
