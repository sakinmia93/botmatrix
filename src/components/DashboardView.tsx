import { BotAvatar } from './BotAvatar';
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Users,
  Terminal,
  Bot,
  Zap,
  Clock,
  TrendingUp,
  Percent,
  CheckCircle2,
  Copy,
  ExternalLink,
  ShieldCheck,
  Server,
  ArrowUpRight,
  Sparkles,
  Info,
  Check,
  Activity,
} from 'lucide-react';
import { BotItem, ActivityHourData } from '../types';
import { apiService } from '../services/apiService';

interface DashboardViewProps {
  bots: BotItem[];
  activityData: ActivityHourData[];
  lastUpdatedTime: string;
  onNavigateToBots: () => void;
  onCreateBotClick: () => void;
  onSelectBot?: (bot: BotItem) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  bots,
  activityData: initialActivityData,
  lastUpdatedTime,
  onNavigateToBots,
  onCreateBotClick,
  onSelectBot,
}) => {
  const [hoveredPoint, setHoveredPoint] = useState<ActivityHourData | null>(null);
  const [copiedBot, setCopiedBot] = useState<string | null>(null);
  const [activityData, setActivityData] = useState<ActivityHourData[]>(initialActivityData);
  const [livePulse, setLivePulse] = useState(false);

  // Sync with initial activityData if passed
  useEffect(() => {
    if (initialActivityData && initialActivityData.length > 0) {
      setActivityData(initialActivityData);
    }
  }, [initialActivityData]);

  // Live telemetry straight from the server: refreshed every 4 s while the page is visible
  const [live, setLive] = useState<any>(null);
  const [liveAt, setLiveAt] = useState<string>('');
  useEffect(() => {
    let stop = false;
    const pull = () => {
      if (document.hidden) return;
      apiService.getDashboardStats().then((st: any) => {
        if (stop || !st) return;
        setLive(st);
        if (Array.isArray(st.activity)) setActivityData(st.activity);
        setLiveAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      }).catch(() => {});
    };
    pull();
    const t = setInterval(pull, 4000);
    const onVis = () => pull();
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('bm_refresh', pull);
    return () => { stop = true; clearInterval(t); document.removeEventListener('visibilitychange', onVis); window.removeEventListener('bm_refresh', pull); };
  }, []);
  const T = live?.totals || {};

  // Everything below comes from the server (falls back to the bot list until the first response)
  const totalBotsCount = T.bots ?? bots.length;
  const workingBotsCount = T.running ?? bots.filter((b) => b.status === 'working').length;
  const totalUsersCount = T.audience ?? bots.reduce((sum, b) => sum + (b.activeUsers || 0), 0);
  const commands24h = T.commands24h ?? 0;
  const peakUsers = activityData.length ? Math.max(0, ...activityData.map((d) => d.users || 0)) : 0;
  const avgPerHour = activityData.length ? Math.round((activityData.reduce((s, d) => s + (d.users || 0), 0) / activityData.length) * 10) / 10 : 0;
  const activeHrs = activityData.filter((d) => (d.users || 0) > 0).length;
  const retentionPct: number | null = T.retention7d ?? null;
  const growthPct: number | null = T.growth24h ?? null;

  const statsLast24h = [
    {
      id: 'stat-active-users',
      label: 'Audience',
      value: totalUsersCount.toLocaleString(),
      change: `${(T.active24h ?? 0).toLocaleString()} active`,
      isPositive: true,
      icon: <Users className="w-5 h-5 text-blue-500" />,
      subtext: `+${(T.newUsers24h ?? 0).toLocaleString()} new in 24 h`,
    },
    {
      id: 'stat-commands-run',
      label: 'Commands run',
      value: commands24h.toLocaleString(),
      change: `${(T.messages24h ?? 0).toLocaleString()} msgs`,
      isPositive: true,
      icon: <Terminal className="w-5 h-5 text-indigo-500" />,
      subtext: `${(T.errors24h ?? 0).toLocaleString()} errors in the last 24 h`,
    },
    {
      id: 'stat-total-bots',
      label: 'Total bots',
      value: totalBotsCount.toLocaleString(),
      change: 'live',
      isPositive: true,
      icon: <Bot className="w-5 h-5 text-purple-500" />,
      subtext: 'In your account',
    },
    {
      id: 'stat-working-bots',
      label: 'Working',
      value: workingBotsCount.toLocaleString(),
      change: T.broadcastsRunning ? `${T.broadcastsRunning} broadcast` : 'live',
      isPositive: true,
      icon: <Zap className="w-5 h-5 text-emerald-500" />,
      subtext: 'Currently polling & answering',
    },
  ];

  // Most active bots dynamically computed from backend bots
  const mostActiveBotsList = (Array.isArray(live?.bots) ? live.bots : [])
    .slice(0, 10)
    .map((b: any) => {
      const base = bots.find((x) => x.id === b.id) || bots.find((x) => x.username && (x.username === b.username || `@${x.username}` === b.username));
      const uname = b.username || base?.username || b.name || 'bot';
      return {
        id: b.id || base?.id,
        username: String(uname).startsWith('@') ? String(uname) : `@${uname}`,
        status: b.status === 'working' ? 'Working' : 'Stopped',
        users: `${b.messages24h ?? 0} msgs · ${b.activeUsers24h ?? 0} users (24 h)`,
        category: base?.category || base?.name || b.name || 'General',
        photoUrl: (base as any)?.photoUrl || (base as any)?.photo || b.photoUrl || null,
      };
    });

  const handleCopy = (username: string) => {
    navigator.clipboard.writeText(username);
    setCopiedBot(username);
    setTimeout(() => setCopiedBot(null), 1800);
  };

  // SVG Chart Dimensions & Calculation
  const chartWidth = Math.max(700, activityData.length * 50);      // 50px per hour so every label stays readable
  // hour label in the viewer's own time zone: 12 AM, 1 AM … 1 PM
  const hourLabel = (d: any) => {
    const t = d?.ts ? new Date(d.ts) : null;
    return t && !isNaN(t.getTime()) ? t.toLocaleTimeString('en-US', { hour: 'numeric', hour12: true }) : d?.time;
  };
  const chartHeight = 220;
  const paddingX = 45;
  const paddingY = 30;
  const maxY = Math.max(3, ...activityData.map((d) => d.users || 0));

  const points = (activityData.length === 0 ? [] : activityData).map((d, index) => {
    const denom = Math.max(1, activityData.length - 1);
    const x = paddingX + (index / denom) * (chartWidth - paddingX * 2);
    const y = chartHeight - paddingY - (d.users / maxY) * (chartHeight - paddingY * 2);
    return { x, y, data: d };
  });

  // Generate SVG path for smooth line
  const pathD = points.length === 0 ? '' : points.reduce((acc, point, index) => {
    if (index === 0) return `M ${point.x} ${point.y}`;
    const prev = points[index - 1];
    const cp1x = prev.x + (point.x - prev.x) / 2;
    const cp1y = prev.y;
    const cp2x = prev.x + (point.x - prev.x) / 2;
    const cp2y = point.y;
    return `${acc} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${point.x} ${point.y}`;
  }, '');

  const areaD = points.length >= 2
    ? `${pathD} L ${points[points.length - 1].x} ${chartHeight - paddingY} L ${points[0].x} ${chartHeight - paddingY} Z`
    : '';

  return (
    <div className="space-y-6 pb-12">
      {/* Top Banner / Live Status Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 text-white p-5 sm:p-6 rounded-3xl shadow-xl shadow-blue-500/10">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full bg-white/20 text-xs font-semibold backdrop-blur-xs flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-300 animate-pulse" />
              Live Cluster Active
            </span>
            <span className="text-xs text-blue-100/90 font-mono">
              Updated: {liveAt || lastUpdatedTime}
            </span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold mt-1.5 tracking-tight">
            Telegram Bot Creator Dashboard
          </h1>
          <p className="text-xs sm:text-sm text-blue-100/90 mt-1 max-w-xl">
            Monitor active bots, track real-time user commands, and supervise webhook routing health across the global node network.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={onCreateBotClick}
            className="px-4 py-2.5 rounded-xl bg-white text-blue-700 font-bold text-xs sm:text-sm shadow-md hover:bg-blue-50 transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <Sparkles className="w-4 h-4 text-blue-600" />
            <span>Create New Bot</span>
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={onNavigateToBots}
            className="px-4 py-2.5 rounded-xl bg-blue-500/30 text-white font-semibold text-xs sm:text-sm hover:bg-blue-500/40 border border-white/20 transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <span>View All Bots</span>
            <ArrowUpRight className="w-4 h-4" />
          </motion.button>
        </div>
      </div>

      {/* SECTION 1: Last 24 hours (Active users 12, Commands run 462, Total bots 404, Working 148) */}
      <div>
        <div className="flex items-center justify-between mb-3 px-1">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide uppercase">
              Last 24 hours
            </h2>
          </div>
          <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
            Live — refreshes every 4 seconds
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {statsLast24h.map((stat, idx) => (
            <motion.div
              key={stat.id}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.08, duration: 0.3 }}
              className="glass-panel p-5 rounded-2xl relative overflow-hidden group hover:border-blue-400/50 transition-all duration-200"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                  {stat.label}
                </span>
                <div className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800/80">
                  {stat.icon}
                </div>
              </div>

              <div className="mt-3 flex items-baseline gap-2">
                <span className="text-3xl font-extrabold text-slate-900 dark:text-white tracking-tight">
                  {stat.value}
                </span>
                <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400 flex items-center">
                  <TrendingUp className="w-3.5 h-3.5 mr-0.5 inline" />
                  {stat.change}
                </span>
              </div>

              <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 font-medium">
                {stat.subtext}
              </p>

              {/* Subtle top indicator line */}
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-500 to-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity" />
            </motion.div>
          ))}
        </div>
      </div>

      {/* SECTION 2: Activity Chart & Engagement Statistics */}
      <div className="glass-panel p-6 rounded-3xl space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
              <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                Activity
              </h2>
            </div>
            <p className="text-xs text-slate-700 dark:text-slate-300 mt-0.5 font-medium">
              Continuous 24-hour command &amp; user concurrency profile
            </p>
          </div>

          {/* Scale indicator legend */}
          <div className="flex items-center gap-4 text-xs font-semibold text-slate-700 dark:text-slate-300">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping inline-block" />
              <span className="text-emerald-600 dark:text-emerald-400 font-bold">Live Stream</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-md bg-blue-500/30 border border-blue-500 inline-block" />
              Active users per hour (0 – {Math.ceil(maxY)})
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-blue-100 dark:bg-blue-950/70 text-blue-700 dark:text-blue-300 font-bold text-xs">
              {peakUsers > 0 ? `Peak ${peakUsers} users / hour` : 'No activity yet'}
            </span>
          </div>
        </div>

        {/* Visual SVG Activity Chart */}
        <div className="relative w-full overflow-x-auto">
          <div className="relative" style={{ minWidth: Math.max(640, activityData.length * 50) }}>
            <svg
              viewBox={`0 0 ${chartWidth} ${chartHeight}`}
              className="w-full h-56 overflow-visible"
            >
              <defs>
                <linearGradient id="activityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Y-axis Horizontal Gridlines (0, 0.75, 1.5, 2.25, 3) */}
              {[0, 0.25, 0.5, 0.75, 1].map((f) => f * maxY).map((val) => {
                const yPos = chartHeight - paddingY - (val / maxY) * (chartHeight - paddingY * 2);
                return (
                  <g key={`y-${val}`}>
                    <line
                      x1={paddingX}
                      y1={yPos}
                      x2={chartWidth - paddingX}
                      y2={yPos}
                      stroke="currentColor"
                      strokeDasharray="4 4"
                      className="text-slate-300 dark:text-slate-800"
                    />
                    <text
                      x={paddingX - 10}
                      y={yPos + 4}
                      textAnchor="end"
                      className="fill-slate-700 dark:fill-slate-300 text-xs font-bold font-mono"
                    >
                      {Number.isInteger(val) ? val : val.toFixed(1)}
                    </text>
                  </g>
                );
              })}

              {/* Shaded Area under Curve - Animated */}
              <motion.path
                d={areaD}
                fill="url(#activityGradient)"
                transition={{ duration: 0.8, ease: 'easeInOut' }}
              />

              {/* Trend Line - Animated */}
              <motion.path
                d={pathD}
                fill="none"
                stroke="#2563eb"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                transition={{ duration: 0.8, ease: 'easeInOut' }}
              />

              {/* Points & Hover targets */}
              {points.map((p, idx) => (
                <g key={`pt-${idx}`}>
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={idx === points.length - 1 ? '6' : '4.5'}
                    className={`${
                      idx === points.length - 1
                        ? 'fill-blue-600 stroke-white stroke-2 animate-pulse'
                        : 'fill-white dark:fill-slate-900 stroke-blue-600 stroke-2'
                    } cursor-pointer transition-transform hover:scale-150`}
                    onMouseEnter={() => setHoveredPoint(p.data)}
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                  {/* X-axis tick labels */}
                  <text
                    x={p.x}
                    y={chartHeight - 8}
                    textAnchor="middle"
                    className="fill-slate-800 dark:fill-slate-200 text-xs font-bold"
                  >
                    {hourLabel(p.data)}
                  </text>
                </g>
              ))}
            </svg>

            {/* Hover Tooltip */}
            {hoveredPoint && (
              <div className="absolute top-2 right-4 px-3 py-1.5 rounded-xl bg-slate-900 text-white text-xs shadow-lg flex items-center gap-2 border border-slate-700">
                <span className="font-bold text-blue-400">{hourLabel(hoveredPoint)}</span>
                <span>{hoveredPoint.users} Active Users</span>
                <span className="text-slate-300 font-medium">({hoveredPoint.commands} cmds)</span>
              </div>
            )}
          </div>
        </div>

        {/* Chart Summary Metrics Row (Users: 12, Peak hour: 3, Avg / hour: 1, Active hrs: 6/24, Retention & Growth) */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
          <div className="p-3 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800/80">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
              Users
            </span>
            <span className="text-xl font-bold text-slate-900 dark:text-white mt-0.5 block">
              {totalUsersCount}
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Total audience</span>
          </div>

          <div className="p-3 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800/80">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
              Peak hour
            </span>
            <span className="text-xl font-bold text-blue-600 dark:text-blue-400 mt-0.5 block">
              {peakUsers}
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Most active users in an hour</span>
          </div>

          <div className="p-3 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800/80">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
              Avg / hour
            </span>
            <span className="text-xl font-bold text-slate-900 dark:text-white mt-0.5 block">
              {avgPerHour}
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Avg users / hour</span>
          </div>

          <div className="p-3 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800/80">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
              Active hrs
            </span>
            <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-0.5 block">
              {activeHrs}/24
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Hours with activity</span>
          </div>

          {/* Retention Rate Column requested */}
          <div className="p-3 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800/80">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
              Retention rate
            </span>
            <span className="text-xl font-bold text-indigo-600 dark:text-indigo-400 mt-0.5 block">
              {retentionPct === null ? '—' : `${retentionPct}%`}
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">
              Active in the last 7 days
            </span>
          </div>

          {/* Growth Percentage Column requested */}
          <div className="p-3 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800/80">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
              Growth %
            </span>
            <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-0.5 block">
              {growthPct === null ? '—' : `${growthPct > 0 ? '+' : ''}${growthPct}%`}
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">New users vs. previous 24 h</span>
          </div>
        </div>

        {/* Concise summary / text-based insight requested */}
        <div className="p-4 rounded-2xl bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900/50 flex items-start gap-3">
          <div className="p-1.5 rounded-lg bg-blue-600 text-white shrink-0 mt-0.5">
            <Info className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-blue-950 dark:text-blue-100">
              Engagement Insight &amp; Concurrency Analysis
            </h4>
            <p className="text-xs text-blue-950 dark:text-blue-200 mt-1 leading-relaxed font-medium">
              {bots.length === 0 ? "No activity yet — create and start a bot to see live metrics." : `Tracking ${totalBotsCount} bot(s), ${workingBotsCount} working. ${(T.active24h ?? 0).toLocaleString()} of ${totalUsersCount.toLocaleString()} users were active in the last 24 hours, ${(T.messages24h ?? 0).toLocaleString()} messages and ${commands24h.toLocaleString()} commands were handled.`}
            </p>
          </div>
        </div>
      </div>

      {/* SECTION 3: Two-Column Section: Most Active Bots & Bots Lifecycle / Uptime */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Most Active Bots Card */}
        <div className="glass-panel p-6 rounded-3xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  Most active bots
                </h3>
                <p className="text-xs text-slate-700 dark:text-slate-300 mt-0.5 font-medium">
                  Top performing bots sorted by live user sessions
                </p>
              </div>
              <button
                onClick={onNavigateToBots}
                className="text-xs text-blue-600 dark:text-blue-400 font-bold hover:underline flex items-center gap-1"
              >
                <span>Manage all</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* List of 5 requested active bots */}
            <div className="space-y-2.5">
              {mostActiveBotsList.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-slate-400 gap-3">
                  <Bot className="w-10 h-10 opacity-40" />
                  <p className="text-sm font-medium">Currently no active bots</p>
                  <p className="text-xs text-slate-500">Create or start a bot to see it here</p>
                </div>
              ) : (
                mostActiveBotsList.map((bot, idx) => {
                const matchedBot =
                  bots.find((b) => b.username === bot.username || `@${b.username}` === bot.username || b.username === bot.username?.replace(/^@/, '')) ||
                  bots.find((b) => b.name && bot.username && bot.username.includes(b.name));
                const photo = bot.photoUrl || (matchedBot as any)?.photoUrl || (matchedBot as any)?.photo || (matchedBot as any)?.avatarUrl || null;
                const isWorking = bot.status === 'Working';
                return (
                  <div
                    key={bot.username + String(idx)}
                    onClick={() => {
                      if (matchedBot && onSelectBot) {
                        onSelectBot(matchedBot);
                      } else {
                        onNavigateToBots();
                      }
                    }}
                    className="p-3 rounded-2xl bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/80 transition-colors shadow-xs cursor-pointer group min-w-0 overflow-hidden"
                  >
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className="relative shrink-0">
                        <BotAvatar
                          src={photo}
                          alt={bot.username}
                          className="w-10 h-10 rounded-xl shadow-sm"
                          iconClassName="w-5 h-5"
                        />
                        <span className="absolute -bottom-1 -right-1 text-[9px] font-black px-1 py-0.5 rounded-md bg-slate-900/80 text-white leading-none">
                          #{idx + 1}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="font-bold text-xs sm:text-sm text-slate-900 dark:text-white truncate group-hover:text-blue-600 transition-colors">
                            {bot.username}
                          </span>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCopy(bot.username);
                            }}
                            title="Copy username"
                            className="text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 p-0.5 shrink-0"
                          >
                            {copiedBot === bot.username ? (
                              <Check className="w-3.5 h-3.5 text-emerald-500" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 mt-1">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                              isWorking
                                ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300'
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                            }`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${isWorking ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'}`} />
                            {bot.status}
                          </span>
                          <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium truncate max-w-full">
                            {bot.category}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="sm:text-right min-w-0 pl-[3.25rem] sm:pl-0">
                      <span className="inline-block max-w-full px-2.5 py-1 rounded-lg text-[10px] sm:text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 font-mono break-words">
                        {bot.users}
                      </span>
                    </div>
                  </div>
                );
              })
              )}
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs text-slate-700 dark:text-slate-300 font-medium">
            <span>{bots.length} bot{bots.length === 1 ? '' : 's'} in your account</span>
            <span className="text-emerald-700 dark:text-emerald-400 font-bold">
              {workingBotsCount > 0 ? `${workingBotsCount} working` : 'No bots running'}
            </span>
          </div>
        </div>

        {/* Bot Templates & Reliability Metrics Card */}
        <div className="glass-panel p-6 rounded-3xl flex flex-col justify-between space-y-6">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  Bots &amp; Infrastructure
                </h3>
                <p className="text-xs text-slate-700 dark:text-slate-300 mt-0.5 font-medium">
                  Store clones, received copies and live performance
                </p>
              </div>
              <span className="p-2 rounded-xl bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-400">
                <Server className="w-4 h-4" />
              </span>
            </div>

            {/* Cloned from the store (70) & Transferred to you (89) */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="p-4 rounded-2xl bg-gradient-to-br from-slate-100 to-blue-50/70 dark:from-slate-800/40 dark:to-blue-950/20 border border-slate-200 dark:border-slate-800">
                <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
                  Cloned from templates
                </span>
                <span className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mt-1 block">{T.fromStore ?? 0}</span>
                <span className="text-xs text-blue-700 dark:text-blue-400 font-bold">
                  Bot Store clones
                </span>
              </div>

              <div className="p-4 rounded-2xl bg-gradient-to-br from-slate-100 to-indigo-50/70 dark:from-slate-800/40 dark:to-indigo-950/20 border border-slate-200 dark:border-slate-800">
                <span className="text-xs font-bold text-slate-700 dark:text-slate-300 block">
                  Transferred to you
                </span>
                <span className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mt-1 block">{T.transferredIn ?? 0}</span>
                <span className="text-xs text-indigo-700 dark:text-indigo-400 font-bold">
                  Copies you accepted
                </span>
              </div>
            </div>

            {/* Uptime & Response Time */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="p-4 rounded-2xl bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    Error rate (24 h)
                  </span>
                  <ShieldCheck className="w-4 h-4 text-emerald-500" />
                </div>
                <span className="text-2xl font-black text-emerald-600 dark:text-emerald-400 mt-1 block">
                  {T.errorRate24h === null || T.errorRate24h === undefined ? '—' : `${T.errorRate24h}%`}
                </span>
                <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">{(T.errors24h ?? 0).toLocaleString()} failed of {commands24h.toLocaleString()} commands</span>
              </div>

              <div className="p-4 rounded-2xl bg-white dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                    Response time
                  </span>
                  <Zap className="w-4 h-4 text-amber-500" />
                </div>
                <span className="text-2xl font-black text-blue-600 dark:text-blue-400 mt-1 block">
                  {T.avgResponseMs === null || T.avgResponseMs === undefined ? '—' : `${T.avgResponseMs} ms`}
                </span>
                <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Average command run time</span>
              </div>
            </div>

            {/* Prompt's exact text requirement:
                "{T.avgResponseMs == null ? "No response-time data yet — it appears after your bots run their first commands." : `Measured on real commands run by your bots in the last 24 hours (${commands24h.toLocaleString()} runs).`}" */}
            <div className="p-4 rounded-2xl bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80">
              <p className="text-xs text-slate-900 dark:text-slate-200 leading-relaxed font-medium">
                <strong className="text-slate-950 dark:text-white font-bold">Latency Benchmark </strong>
                {T.avgResponseMs == null ? "No response-time data yet — it appears after your bots run their first commands." : `Measured on real commands run by your bots in the last 24 hours (${commands24h.toLocaleString()} runs).`}
              </p>
            </div>
          </div>

          <div className="pt-2 flex items-center justify-between">
            <span className="text-xs text-slate-700 dark:text-slate-300 font-semibold">
              Account Status
            </span>
            <span className="text-xs font-bold text-blue-700 dark:text-blue-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              {totalBotsCount > 0 ? `${workingBotsCount}/${totalBotsCount} running` : 'No bots'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
