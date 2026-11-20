import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Trash2,
  RefreshCw,
  ArrowRight,
  RotateCcw,
  DollarSign,
  TrendingUp,
  CreditCard,
  Wallet,
  ArrowLeft,
  ArrowLeftRight,
  ShieldCheck,
  Key,
  Globe,
  Sliders,
  HelpCircle,
  Headphones,
  CheckCircle2,
  Send,
  ExternalLink,
  MessageSquare,
  Bot,
  History,
  Search,
  Copy,
  Check,
  FileText,
  Calendar,
  CheckCircle,
  Clock,
  Sparkles,
  X,
  Lock,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Code,
  Radio,
  Layers,
  Terminal,
  LifeBuoy,
  User as UserIcon,
  BookOpen,
  Hash,
  ShieldAlert,
} from 'lucide-react';
import { BotItem, NotificationItem, User, TransferHistoryRecord } from '../types';
import { ConfirmationModal } from './ConfirmationModal';
import { apiService } from '../services/apiService'
import { SupportChat } from './SupportChat';

export { SettingsView } from './SettingsView';

/* 1. RECYCLE BIN VIEW */
interface RecycleBinViewProps {
  recycleBots: BotItem[];
  onRestoreBot: (id: string) => void;
  onPermanentlyDelete: (id: string) => void;
  onEmptyRecycleBin: () => void;
}

export const RecycleBinView: React.FC<RecycleBinViewProps> = ({
  recycleBots,
  onRestoreBot,
  onPermanentlyDelete,
  onEmptyRecycleBin,
}) => {
  const [showEmptyConfirm, setShowEmptyConfirm] = useState(false);
  const [botToDeleteForever, setBotToDeleteForever] = useState<BotItem | null>(null);

  // Helper to calculate days elapsed & remaining retention
  const getRetentionInfo = (deletedAt?: string) => {
    const delDate = deletedAt ? new Date(deletedAt).getTime() : Date.now();
    const daysPassed = (Date.now() - delDate) / (1000 * 60 * 60 * 24);
    const daysRemaining = Math.max(0, 10 - daysPassed);
    const isLocked = daysRemaining > 0;
    return {
      daysRemaining: Math.ceil(daysRemaining),
      isLocked,
      delDateStr: new Date(delDate).toLocaleDateString(),
    };
  };

  const eligibleCount = recycleBots.filter((b) => !getRetentionInfo(b.deletedAt).isLocked).length;

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
              Recycle Bin
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800 flex items-center gap-1">
              <Lock className="w-3 h-3" />
              10-Day Retention Hold Policy
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 mt-1 font-medium">
            Bots deleted are safely protected for a mandatory 10-day retention period. You can restore your bot anytime. Permanent deletion is locked until 10 days have elapsed.
          </p>
        </div>

        {recycleBots.length > 0 && (
          <button
            onClick={() => setShowEmptyConfirm(true)}
            className="px-4 py-2 rounded-xl bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-900/50 text-xs font-bold hover:bg-rose-100 transition-colors flex items-center gap-1.5 self-start sm:self-auto cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Empty Recycle Bin</span>
          </button>
        )}
      </div>

      {recycleBots.length === 0 ? (
        <div className="glass-panel p-12 text-center rounded-3xl">
          <Trash2 className="w-12 h-12 text-slate-400 dark:text-slate-500 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
            Recycle Bin is empty
          </h3>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 font-medium">
            No bots have been moved to the recycle bin.
          </p>
        </div>
      ) : (
        <div className="glass-panel rounded-2xl overflow-hidden divide-y divide-slate-200 dark:divide-slate-800">
          {recycleBots.map((bot) => {
            const retention = getRetentionInfo(bot.deletedAt);
            return (
              <div
                key={bot.id}
                className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-100/60 dark:hover:bg-slate-800/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-rose-100 dark:bg-rose-950/50 text-rose-600 flex items-center justify-center font-bold">
                    <Bot className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                      {bot.name}
                    </h4>
                    <p className="text-xs text-slate-600 dark:text-slate-400 font-medium">
                      {bot.username} • {bot.category || 'Operations'} • Moved: {retention.delDateStr}
                    </p>
                    <div className="mt-1 flex items-center gap-2">
                      {retention.isLocked ? (
                        <span className="px-2 py-0.5 rounded-md bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 text-[10px] font-bold border border-amber-200 dark:border-amber-800 flex items-center gap-1">
                          <Lock className="w-2.5 h-2.5" />
                          Locked: Available for permanent delete in {retention.daysRemaining} day{retention.daysRemaining === 1 ? '' : 's'}
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-md bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 text-[10px] font-bold border border-emerald-200 dark:border-emerald-800 flex items-center gap-1">
                          <CheckCircle2 className="w-2.5 h-2.5" />
                          Retention period completed (Eligible to purge)
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-auto">
                  <button
                    onClick={() => onRestoreBot(bot.id)}
                    className="px-3.5 py-1.5 rounded-xl bg-blue-100 dark:bg-blue-950/50 text-blue-700 dark:text-blue-400 text-xs font-bold hover:bg-blue-200 flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Restore Bot</span>
                  </button>

                  <button
                    onClick={() => {
                      if (!retention.isLocked) {
                        setBotToDeleteForever(bot);
                      }
                    }}
                    disabled={retention.isLocked}
                    title={
                      retention.isLocked
                        ? `Permanent deletion locked: Must wait 10 days (${retention.daysRemaining} days remaining)`
                        : 'Permanently delete bot'
                    }
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-colors ${
                      retention.isLocked
                        ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 cursor-not-allowed opacity-60'
                        : 'bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/50 text-rose-700 dark:text-rose-400 cursor-pointer'
                    }`}
                  >
                    {retention.isLocked && <Lock className="w-3 h-3 text-slate-400" />}
                    <span>{retention.isLocked ? `Locked (${retention.daysRemaining}d)` : 'Delete Forever'}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Confirmation Modals for Destructive Actions */}
      <ConfirmationModal
        isOpen={showEmptyConfirm}
        onClose={() => setShowEmptyConfirm(false)}
        onConfirm={onEmptyRecycleBin}
        title="Empty Recycle Bin"
        message={
          eligibleCount > 0
            ? `Are you sure you want to permanently delete ${eligibleCount} eligible bot(s)? Items under the 10-day retention lock will remain protected.`
            : `All ${recycleBots.length} bot(s) in the recycle bin are currently protected by the mandatory 10-day retention safety hold and cannot be deleted yet.`
        }
        confirmText={eligibleCount > 0 ? 'Yes, Delete Eligible' : 'Understood'}
        cancelText="Cancel"
        isDestructive={eligibleCount > 0}
      />

      <ConfirmationModal
        isOpen={botToDeleteForever !== null}
        onClose={() => setBotToDeleteForever(null)}
        onConfirm={() => {
          if (botToDeleteForever) {
            onPermanentlyDelete(botToDeleteForever.id);
            setBotToDeleteForever(null);
          }
        }}
        title="Permanently Delete Bot"
        message={`Are you sure you want to permanently delete "${botToDeleteForever?.name}" (${botToDeleteForever?.username})? The 10-day retention hold has passed. All commands and data will be destroyed forever.`}
        confirmText="Yes, Delete Forever"
        cancelText="Cancel"
        isDestructive={true}
      />
    </div>
  );
};

/* 2. MONETIZATION VIEW */
export const MonetizationView: React.FC = () => {
  return (
    <div className="space-y-6 pb-12">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
          Bot Monetization &amp; Revenue
        </h1>
        <p className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 mt-1 font-medium">
          Collect Telegram Stars, monthly subscriber fees, and digital payments across your bots.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-panel p-5 rounded-2xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
              Total Earnings
            </span>
            <Wallet className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
          </div>
          <span className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mt-2 block">
            $2,480.50
          </span>
          <span className="text-xs text-emerald-700 dark:text-emerald-400 font-bold mt-1 inline-block">
            +32.4% this month
          </span>
        </div>

        <div className="glass-panel p-5 rounded-2xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
              Telegram Stars
            </span>
            <DollarSign className="w-5 h-5 text-amber-500" />
          </div>
          <span className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mt-2 block">
            18,450 ★
          </span>
          <span className="text-xs text-slate-600 dark:text-slate-400 font-medium mt-1 inline-block">
            Ready to withdraw
          </span>
        </div>

        <div className="glass-panel p-5 rounded-2xl">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
              Active Subscriptions
            </span>
            <CreditCard className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
          </div>
          <span className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white mt-2 block">
            348
          </span>
          <span className="text-xs text-blue-700 dark:text-blue-400 font-bold mt-1 inline-block">
            Recurring members
          </span>
        </div>
      </div>

      <div className="glass-panel p-6 rounded-3xl space-y-4">
        <h3 className="text-base font-bold text-slate-900 dark:text-white">
          Payment Gateways Connected
        </h3>
        <div className="space-y-3">
          <div className="p-4 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <div>
              <p className="font-bold text-sm text-slate-900 dark:text-white">
                Telegram Stars Native API
              </p>
              <p className="text-xs text-slate-600 dark:text-slate-400 font-medium">
                In-app digital goods for mobile &amp; desktop users
              </p>
            </div>
            <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
              Connected
            </span>
          </div>

          <div className="p-4 rounded-2xl bg-slate-100/90 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <div>
              <p className="font-bold text-sm text-slate-900 dark:text-white">
                Crypto Pay &amp; TON Connect
              </p>
              <p className="text-xs text-slate-600 dark:text-slate-400 font-medium">
                USDT, TON, and BTC instant settlements
              </p>
            </div>
            <span className="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
              Active
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

/* 3. TRANSFERS VIEW (WITH 30-DAY TRANSFER HISTORY SYSTEM) */
const relTime = (iso?: string | null) => {
  if (!iso) return '';
  const s = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
const expiresText = (iso?: string | null) => {
  if (!iso) return '';
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return 'expired';
  const h = Math.floor(ms / 3600000);
  return h >= 24 ? `expires in ${Math.floor(h / 24)}d` : `expires in ${Math.max(1, h)}h`;
};

const ReceiptLink: React.FC<{ transferId: string }> = ({ transferId }) => {
  const [url, setUrl] = useState('');
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let alive = true;
    setUrl('');
    apiService.getTransferReceiptCode(transferId).then((r) => alive && setUrl(`${window.location.origin}/receipt/${r.code}`)).catch(() => {});
    return () => { alive = false; };
  }, [transferId]);
  return (
    <div className="space-y-1.5">
      <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">Public receipt link</label>
      <div className="p-3 rounded-xl bg-slate-100 dark:bg-slate-800 font-mono text-[11px] text-slate-800 dark:text-slate-200 break-all select-all border border-slate-200 dark:border-slate-700">
        {url || 'Creating link…'}
      </div>
      <div className="flex gap-2">
        <button type="button" disabled={!url} onClick={() => { navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1800); }}
          className="px-3 py-1.5 rounded-xl bg-blue-600 text-white text-xs font-bold disabled:opacity-50 cursor-pointer">{copied ? 'Copied' : 'Copy link'}</button>
        <a href={url || undefined} target="_blank" rel="noopener noreferrer"
          className="px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs font-bold">Open</a>
      </div>
      <p className="text-[11px] text-slate-500">Anyone with this link can verify the transfer without logging in. It never shows tokens or bot data.</p>
    </div>
  );
};

export const TransfersView: React.FC = () => {
  type SubTab = 'history30d' | 'incoming' | 'outgoing';
  const [activeSubTab, setActiveSubTabState] = useState<SubTab>(() => {
    try {
      const v = localStorage.getItem('bm_transfers_tab') as SubTab | null;
      if (v === 'history30d' || v === 'incoming' || v === 'outgoing') return v;
    } catch {}
    return 'history30d';
  });
  const setActiveSubTab = (t: SubTab) => {
    setActiveSubTabState(t);
    try { localStorage.setItem('bm_transfers_tab', t); } catch {}
  };
  const [historyRecords, setHistoryRecords] = useState<TransferHistoryRecord[]>([]);
  const [incomingTransfers, setIncomingTransfers] = useState<{
    id: string; botName: string; botNumericId: string; sender: string; date: string; expiresIn: string; status: 'pending' | 'accepted' | 'rejected';
  }[]>([]);
  const [outgoingTransfers, setOutgoingTransfers] = useState<{
    id: string; botName: string; botNumericId: string; recipient: string; date: string; expiresIn: string; status: 'pending' | 'accepted' | 'rejected';
  }[]>([]);
  const [limits, setLimits] = useState<{ perTenMinutes: number; used: number; remaining: number } | null>(null);
  const [transferToast, setTransferToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await apiService.getTransfers();
      const all = [...(d.incoming || []), ...(d.outgoing || []), ...(d.history || [])]
        .sort((a: any, b: any) => String(b.createdAt).localeCompare(String(a.createdAt)));
      setHistoryRecords(all.map((t: any) => ({
        id: t.id, botId: t.botId, botName: t.botName, botNumericId: t.botNumericId || '', type: t.direction,
        sender: t.fromEmail, recipient: t.toEmail, date: new Date(t.createdAt).toLocaleString(), relativeTime: relTime(t.createdAt),
        status: t.status === 'accepted' ? 'completed' : t.status === 'rejected' ? 'cancelled' : t.status,
        tokenHash: t.verificationToken || '', commandsCount: t.commandsCount || 0, foldersCount: 0,
      })));
      setIncomingTransfers((d.incoming || []).map((t: any) => ({
        id: t.id, botName: t.botName, botNumericId: t.botNumericId || '', sender: t.fromEmail,
        date: relTime(t.createdAt), expiresIn: expiresText(t.expiresAt), status: 'pending' as const,
      })));
      setOutgoingTransfers((d.outgoing || []).map((t: any) => ({
        id: t.id, botName: t.botName, botNumericId: t.botNumericId || '', recipient: t.toEmail,
        date: relTime(t.createdAt), expiresIn: expiresText(t.expiresAt), status: 'pending' as const,
      })));
      setLimits(d.limits || null);
    } catch {}
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(() => { if (!document.hidden) load(); }, 8000);
    return () => clearInterval(t);
  }, [load]);

  // History filtering & search
  const [searchQuery, setSearchQuery] = useState('');
  const [historyFilter, setHistoryFilter] = useState<'all' | 'incoming' | 'outgoing' | 'completed' | 'pending'>('all');
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [selectedAuditRecord, setSelectedAuditRecord] = useState<TransferHistoryRecord | null>(null);

  const showToast = (msg: string) => {
    setTransferToast(msg);
    setTimeout(() => setTransferToast(null), 3200);
  };

  const handleCopyToken = (token: string) => {
    navigator.clipboard.writeText(token);
    setCopiedToken(token);
    showToast('Transfer verification token copied!');
    setTimeout(() => setCopiedToken(null), 2000);
  };

  const respond = async (id: string, action: 'accept' | 'reject' | 'cancel', okMsg: string) => {
    try {
      await apiService.respondTransfer(id, action);
      showToast(okMsg);
      if (action === 'accept') window.dispatchEvent(new CustomEvent('bm_refresh'));
    } catch (err: any) {
      showToast(err?.response?.data?.error || 'Something went wrong. Please try again.');
    }
    load();
  };

  const handleAccept = (id: string, name: string) => respond(id, 'accept', `Accepted transfer of ${name}`);
  const handleReject = (id: string, name: string) => respond(id, 'reject', `Rejected transfer of ${name}`);
  const handleCancelOutgoing = (id: string, name: string) => respond(id, 'cancel', `Cancelled outgoing transfer of ${name}`);

  const handleCancelAllOutgoing = async () => {
    if (!window.confirm('Are you sure you want to cancel all outgoing transfer requests?')) return;
    for (const t of outgoingTransfers) {
      try { await apiService.respondTransfer(t.id, 'cancel'); } catch {}
    }
    showToast('Cancelled all outgoing transfer requests');
    load();
  };

  // Filtered 30-day history records
  const filteredHistory = historyRecords.filter((rec) => {
    const matchesSearch =
      rec.botName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rec.botNumericId.includes(searchQuery) ||
      rec.sender.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rec.recipient.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rec.tokenHash.toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;

    if (historyFilter === 'all') return true;
    if (historyFilter === 'incoming') return rec.type === 'incoming';
    if (historyFilter === 'outgoing') return rec.type === 'outgoing';
    if (historyFilter === 'completed') return rec.status === 'completed';
    if (historyFilter === 'pending') return rec.status === 'pending';
    return true;
  });

  return (
    <div className="space-y-6 pb-16 max-w-5xl mx-auto">
      {transferToast && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-4 py-2.5 rounded-2xl shadow-2xl text-xs font-bold flex items-center gap-2 border border-slate-700/40">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 dark:text-emerald-600" />
          <span>{transferToast}</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white tracking-tight">
            Bot Transfers &amp; Ownership
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
            Review live transfer requests and audit full bot handover activity over the last 30 days.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3.5 py-1.5 rounded-xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 text-xs font-bold flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            30-Day Audit Trail Active
          </span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-panel p-5 rounded-3xl border border-slate-200/80 dark:border-slate-800/80">
          <span className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            30-Day Transfers
          </span>
          <span className="text-3xl font-black text-slate-900 dark:text-white mt-2 block">
            {historyRecords.length} Bots
          </span>
          <p className="text-xs text-emerald-600 dark:text-emerald-400 font-bold mt-1 flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5" />
            Every handover is logged
          </p>
        </div>

        <div className="glass-panel p-5 rounded-3xl border border-slate-200/80 dark:border-slate-800/80">
          <span className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            Incoming Requests
          </span>
          <span className="text-3xl font-black text-blue-600 dark:text-blue-400 mt-2 block">
            {incomingTransfers.filter((t) => t.status === 'pending').length} Pending
          </span>
          <p className="text-xs text-slate-500 mt-1">
            Auto-expires 3 days after the request
          </p>
        </div>

        <div className="glass-panel p-5 rounded-3xl border border-slate-200/80 dark:border-slate-800/80">
          <span className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
            Outgoing Handover
          </span>
          <span className="text-3xl font-black text-slate-900 dark:text-white mt-2 block">
            {outgoingTransfers.filter((t) => t.status === 'pending').length} Outgoing
          </span>
          <p className="text-xs text-slate-500 mt-1">
            Awaiting recipient authorization
          </p>
        </div>
      </div>

      {/* Tabs for 30-Day History vs Incoming vs Outgoing */}
      <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
            <button
              onClick={() => setActiveSubTab('history30d')}
              className={`px-4 py-2.5 rounded-2xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 whitespace-nowrap ${
                activeSubTab === 'history30d'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              <History className="w-4 h-4" />
              <span>Last 30 Days History</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/20 font-mono">
                {historyRecords.length}
              </span>
            </button>

            <button
              onClick={() => setActiveSubTab('incoming')}
              className={`px-4 py-2.5 rounded-2xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 whitespace-nowrap ${
                activeSubTab === 'incoming'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              <ArrowLeftRight className="w-4 h-4" />
              <span>Incoming Requests</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-mono">
                {incomingTransfers.length}
              </span>
            </button>

            <button
              onClick={() => setActiveSubTab('outgoing')}
              className={`px-4 py-2.5 rounded-2xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 whitespace-nowrap ${
                activeSubTab === 'outgoing'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              <Send className="w-4 h-4" />
              <span>Outgoing Requests</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-mono">
                {outgoingTransfers.length}
              </span>
            </button>
          </div>
        </div>

        {/* 1. LAST 30 DAYS TRANSFER HISTORY VIEW */}
        {activeSubTab === 'history30d' && (
          <div className="space-y-4">
            {/* Search and Filter Chips */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="relative flex-1 max-w-md">
                <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search 30-day transfers by bot name, ID, or user..."
                  className="w-full pl-10 pr-4 py-2.5 rounded-2xl text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>

              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
                {(['all', 'incoming', 'outgoing', 'completed', 'pending'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setHistoryFilter(f)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold capitalize transition-colors cursor-pointer whitespace-nowrap ${
                      historyFilter === f
                        ? 'bg-slate-900 dark:bg-white text-white dark:text-slate-900'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>

            {/* List of 30-Day Records */}
            {filteredHistory.length === 0 ? (
              <div className="p-8 text-center rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-dashed border-slate-300 dark:border-slate-700 space-y-2">
                <p className="text-xs font-bold text-slate-700 dark:text-slate-300">
                  No transfer records found matching your filters
                </p>
                <p className="text-[11px] text-slate-500">
                  Try clearing your search query or selecting &quot;All&quot; filter.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredHistory.map((rec) => (
                  <div
                    key={rec.id}
                    className="p-4 sm:p-5 rounded-2xl bg-white dark:bg-slate-800/60 border border-slate-200/90 dark:border-slate-700/60 hover:border-slate-300 dark:hover:border-slate-600 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                  >
                    <div className="space-y-1.5 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm font-bold text-slate-900 dark:text-white">
                          {rec.botName}
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-700 font-mono text-slate-600 dark:text-slate-300">
                          ID: {rec.botNumericId}
                        </span>
                        <span
                          className={`text-[10px] px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider ${
                            rec.type === 'incoming'
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-indigo-100 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400'
                          }`}
                        >
                          {rec.type === 'incoming' ? 'Incoming Transferred' : 'Outgoing Handover'}
                        </span>
                      </div>

                      <p className="text-xs text-slate-500">
                        From <strong className="text-slate-800 dark:text-slate-200">{rec.sender}</strong> → To <strong className="text-slate-800 dark:text-slate-200">{rec.recipient}</strong>
                      </p>

                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-400 font-mono">
                        <span>{rec.date} ({rec.relativeTime})</span>
                        <span>•</span>
                        <span>{rec.commandsCount} commands</span>
                        <span>•</span>
                        <span>{rec.foldersCount} folders</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2.5 shrink-0">
                      {/* Status pill */}
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-bold ${
                          rec.status === 'completed'
                            ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400'
                            : rec.status === 'pending'
                            ? 'bg-amber-100 dark:bg-amber-950 text-amber-600 dark:text-amber-400'
                            : 'bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-400'
                        }`}
                      >
                        {rec.status.toUpperCase()}
                      </span>

                      {/* Token hash copy button */}
                      <button
                        type="button"
                        onClick={() => handleCopyToken(rec.tokenHash)}
                        title="Copy cryptographic proof token"
                        className="px-2.5 py-1 rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-600 dark:text-slate-300 text-[11px] font-mono flex items-center gap-1 cursor-pointer transition-colors"
                      >
                        {copiedToken === rec.tokenHash ? (
                          <Check className="w-3 h-3 text-emerald-500" />
                        ) : (
                          <Copy className="w-3 h-3" />
                        )}
                        <span>{rec.tokenHash.substring(0, 15)}</span>
                      </button>

                      {/* Audit Certificate Modal trigger */}
                      <button
                        type="button"
                        onClick={() => setSelectedAuditRecord(rec)}
                        className="px-3 py-1 rounded-xl bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/60 dark:hover:bg-blue-900/60 text-blue-600 dark:text-blue-400 text-xs font-bold cursor-pointer transition-colors flex items-center gap-1"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        Audit Proof
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 2. INCOMING TRANSFERS VIEW */}
        {activeSubTab === 'incoming' && (
          <div className="space-y-3">
            {incomingTransfers.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No incoming transfers pending.</p>
            ) : (
              incomingTransfers.map((req) => (
                <div
                  key={req.id}
                  className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-slate-900 dark:text-white">
                        {req.botName}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 font-mono">
                        ID: {req.botNumericId}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      From <strong className="text-slate-700 dark:text-slate-300">{req.sender}</strong> • Requested {req.date} • {req.expiresIn}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    {req.status === 'pending' ? (
                      <>
                        <button
                          onClick={() => handleAccept(req.id, req.botName)}
                          className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold cursor-pointer transition-colors shadow-xs"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => handleReject(req.id, req.botName)}
                          className="px-3.5 py-1.5 rounded-xl border border-rose-200 dark:border-rose-900/60 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-xs font-bold cursor-pointer transition-colors"
                        >
                          Reject
                        </button>
                      </>
                    ) : req.status === 'accepted' ? (
                      <span className="px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-600">
                        Accepted
                      </span>
                    ) : (
                      <span className="px-3 py-1 rounded-full text-xs font-bold bg-rose-100 dark:bg-rose-950 text-rose-600">
                        Rejected
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* 3. OUTGOING TRANSFERS VIEW */}
        {activeSubTab === 'outgoing' && (
          <div className="space-y-3">
            {outgoingTransfers.length > 0 && (
              <div className="flex items-center justify-between pb-2 border-b border-slate-200/80 dark:border-slate-800/80">
                <span className="text-xs text-slate-500 font-bold">
                  Active Outgoing Requests ({outgoingTransfers.length})
                </span>
                <button
                  type="button"
                  onClick={handleCancelAllOutgoing}
                  className="px-3 py-1.5 rounded-xl border border-rose-200 dark:border-rose-900/60 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-xs font-bold cursor-pointer transition-colors flex items-center gap-1.5"
                >
                  <X className="w-3.5 h-3.5" />
                  <span>Cancel All</span>
                </button>
              </div>
            )}

            {outgoingTransfers.length === 0 ? (
              <p className="text-xs text-slate-500 text-center py-6">No outgoing transfers active.</p>
            ) : (
              outgoingTransfers.map((req) => (
                <div
                  key={req.id}
                  className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div>
                    <span className="font-mono text-sm font-bold text-slate-900 dark:text-white block">
                      {req.botName}
                    </span>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Transfer to <strong className="text-slate-700 dark:text-slate-300">{req.recipient}</strong> • Auto-expires in {req.expiresIn}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    <span className="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 dark:bg-amber-950 text-amber-600">
                      Pending Approval
                    </span>
                    <button
                      type="button"
                      onClick={() => handleCancelOutgoing(req.id, req.botName)}
                      className="px-3 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/60 dark:hover:bg-rose-900/60 text-rose-600 dark:text-rose-400 text-xs font-bold cursor-pointer transition-colors flex items-center gap-1 shadow-xs"
                      title="Cancel this outgoing request"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Cancel</span>
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Audit Certificate Modal */}
      <AnimatePresence>
        {selectedAuditRecord && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="w-full max-w-lg bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 flex items-center justify-center">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                      Cryptographic Transfer Audit Proof
                    </h3>
                    <p className="text-[11px] text-slate-400">
                      Recorded in last 30 days immutable ledger
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedAuditRecord(null)}
                  className="p-1 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-800/60 space-y-2 border border-slate-200/60 dark:border-slate-700/60">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Bot Entity</span>
                    <span className="font-mono font-bold text-slate-900 dark:text-white">
                      {selectedAuditRecord.botName} (ID {selectedAuditRecord.botNumericId})
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Transfer Type</span>
                    <span className="font-bold text-slate-900 dark:text-white uppercase">
                      {selectedAuditRecord.type}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Sender Party</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">
                      {selectedAuditRecord.sender}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Recipient Party</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">
                      {selectedAuditRecord.recipient}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Timestamp</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">
                      {selectedAuditRecord.date} ({selectedAuditRecord.relativeTime})
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Status</span>
                    <span className="font-bold text-emerald-600 dark:text-emerald-400">
                      {selectedAuditRecord.status.toUpperCase()}
                    </span>
                  </div>
                </div>

                <ReceiptLink transferId={selectedAuditRecord.id} />
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={() => setSelectedAuditRecord(null)}
                  className="px-4 py-2 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-xs font-bold cursor-pointer"
                >
                  Close Receipt
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

const LiveStatus: React.FC = () => {
  const [s, setS] = useState<any>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () => apiService.getStatus().then((d) => { if (alive) { setS(d); setFailed(false); } }).catch(() => alive && setFailed(true));
    load();
    const t = setInterval(() => { if (!document.hidden) load(); }, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);
  const up = (sec: number) => (sec < 3600 ? `${Math.floor(sec / 60)}m` : sec < 86400 ? `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m` : `${Math.floor(sec / 86400)}d ${Math.floor((sec % 86400) / 3600)}h`);
  const ok = !!s && !failed;
  const card = (title: string, value: string, note: string, good = true) => (
    <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 space-y-1">
      <span className="text-[11px] text-slate-400 font-semibold block">{title}</span>
      <span className="text-base font-bold text-slate-900 dark:text-white">{value}</span>
      <span className={`text-[10px] font-bold block ${good ? 'text-emerald-500' : 'text-amber-500'}`}>● {note}</span>
    </div>
  );
  return (
    <div className="glass-panel p-6 rounded-3xl space-y-4 border border-slate-200 dark:border-slate-800">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2"><Radio className="w-5 h-5 text-emerald-500" /><span>Live platform status</span></h3>
        <span className={`px-3 py-1 rounded-full text-xs font-bold ${ok ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300' : 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300'}`}>
          {s ? (failed ? 'Connection lost' : 'Operational') : failed ? 'Unreachable' : 'Checking…'}
        </span>
      </div>
      {s && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-2">
          {card('API server', `Up ${up(s.api.uptimeSec)}`, 'Answering requests', ok)}
          {card('Database', `${s.database.latencyMs} ms`, 'Read latency', s.database.latencyMs < 100)}
          {card('Your bots', `${s.bots.running} of ${s.bots.total} running`, `${s.bots.liveWorkers} live workers`, s.bots.running === s.bots.liveWorkers)}
          {card('Broadcasts', `${s.broadcasts.active} active`, `${s.errors24h} bot errors in 24 h`, s.errors24h === 0)}
        </div>
      )}
    </div>
  );
};

/* 5. HELP & SUPPORT VIEW */
export const HelpSupportView: React.FC<{ mode?: 'help' | 'support' }> = ({ mode = 'help' }) => {
  // mode comes from App tab: Help → docs, Support → tickets only
  const [subTab, setSubTab] = useState<'help' | 'support' | 'status'>(mode === 'support' ? 'support' : 'help');
  const [faqSearch, setFaqSearch] = useState('');
  const [openFaqIndex, setOpenFaqIndex] = useState<number | null>(0);

  // Support ticket system state
  const [ticketsList, setTicketsList] = useState<any[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);
  const [view, setView] = useState<'list' | 'open' | 'detail'>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Open ticket form
  const [subject, setSubject] = useState('');
  const [department, setDepartment] = useState('General');
  const [priority, setPriority] = useState('Normal');
  const [message, setMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  // Reply
  const [replyText, setReplyText] = useState('');
  const [replySending, setReplySending] = useState(false);
  const [peerTyping, setPeerTyping] = useState(false);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const typingActiveRef = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const DEPARTMENTS = [
    'General',
    'Bot Studio & Editor',
    'Billing & Plans',
    'Broadcast',
    'Technical / Bug Report',
    'Account & Security',
  ];
  const PRIORITIES = ['Low', 'Normal', 'High', 'Urgent'];

  const statusStyle = (status: string) => {
    const s = (status || 'open').toLowerCase();
    if (s === 'closed') return 'bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200';
    if (s === 'answered') return 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300';
    if (s === 'customer-reply') return 'bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300';
    return 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300';
  };

  const statusLabel = (status: string) => {
    const s = (status || 'open').toLowerCase();
    if (s === 'customer-reply') return 'Customer Reply';
    if (s === 'answered') return 'Answered';
    if (s === 'closed') return 'Closed';
    return 'Open';
  };

  const priorityStyle = (p: string) => {
    const v = (p || 'Normal').toLowerCase();
    if (v === 'urgent') return 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300';
    if (v === 'high') return 'bg-orange-100 dark:bg-orange-950 text-orange-700 dark:text-orange-300';
    if (v === 'low') return 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300';
    return 'bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300';
  };

  const loadTickets = useCallback(() => {
    setTicketsLoading(true);
    apiService
      .getSupportTickets()
      .then((t) => setTicketsList(Array.isArray(t) ? t : []))
      .catch(() => setTicketsList([]))
      .finally(() => setTicketsLoading(false));
  }, []);

  useEffect(() => {
    if (mode === 'support' || subTab === 'support') loadTickets();
  }, [mode, subTab, loadTickets]);

  const openDetail = async (id: string) => {
    setSelectedId(id);
    setView('detail');
    setDetailLoading(true);
    setActionError(null);
    setReplyText('');
    try {
      const d = await apiService.getSupportTicket(id);
      setTicketDetail(d);
    } catch (e: any) {
      setActionError(e?.message || 'Could not load ticket.');
      setTicketDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleCreateTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    if (!subject.trim()) {
      setFormError('Please add a subject.');
      return;
    }
    if (!message.trim()) {
      setFormError('Please write your message.');
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await apiService.submitSupportTicket({
        subject: subject.trim(),
        department,
        category: department,
        priority,
        message: message.trim(),
      });
      setFormSuccess(res.ticketId);
      setSubject('');
      setMessage('');
      setDepartment('General');
      setPriority('Normal');
      loadTickets();
      setTimeout(() => {
        setFormSuccess(null);
        openDetail(res.ticketId);
      }, 800);
    } catch (err: any) {
      setFormError(err?.message || 'Failed to create ticket.');
    } finally {
      setIsSubmitting(false);
    }
  };


  // Live inbox: while a ticket is open, poll for new admin replies every 3s
  useEffect(() => {
    if (view !== 'detail' || !selectedId) return;
    let alive = true;
    const tick = async () => {
      try {
        const d = await apiService.getSupportTicket(selectedId);
        if (!alive) return;
        setTicketDetail(d);
        setPeerTyping(!!d?.adminTyping);
      } catch (_) {}
    };
    tick();
    const id = window.setInterval(tick, 3000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [view, selectedId]);

  const notifyTyping = (text: string) => {
    setReplyText(text);
    if (!selectedId || (ticketDetail?.status || '').toLowerCase() === 'closed') return;
    const active = text.trim().length > 0;
    if (active) {
      if (!typingActiveRef.current) {
        typingActiveRef.current = true;
        apiService.supportTyping(selectedId, true).catch(() => {});
      }
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      typingTimerRef.current = setTimeout(() => {
        typingActiveRef.current = false;
        apiService.supportTyping(selectedId, false).catch(() => {});
      }, 2000);
    } else if (typingActiveRef.current) {
      typingActiveRef.current = false;
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      apiService.supportTyping(selectedId, false).catch(() => {});
    }
  };

    const handleReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !replyText.trim() || replySending) return;
    if ((ticketDetail?.status || '').toLowerCase() === 'closed') {
      setActionError('This ticket is closed. Reopen it before replying.');
      return;
    }
    setReplySending(true);
    setActionError(null);
    try {
      await apiService.replySupportTicket(selectedId, replyText.trim());
      setReplyText('');
      typingActiveRef.current = false;
      apiService.supportTyping(selectedId, false).catch(() => {});
      const d = await apiService.getSupportTicket(selectedId);
      setTicketDetail(d);
      loadTickets();
    } catch (err: any) {
      setActionError(err?.response?.data?.error || err?.message || 'Failed to send reply.');
    } finally {
      setReplySending(false);
    }
  };

  const handleClose = async () => {
    if (!selectedId) return;
    setActionError(null);
    try {
      await apiService.closeSupportTicket(selectedId);
      const d = await apiService.getSupportTicket(selectedId);
      setTicketDetail(d);
      loadTickets();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to close ticket.');
    }
  };

  const handleReopen = async () => {
    if (!selectedId) return;
    setActionError(null);
    try {
      await apiService.reopenSupportTicket(selectedId);
      const d = await apiService.getSupportTicket(selectedId);
      setTicketDetail(d);
      loadTickets();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to reopen ticket.');
    }
  };

  const faqs = [
    {
      q: 'How do I connect a new Telegram bot via @BotFather?',
      a: 'Open Telegram, start a chat with @BotFather, and run the /newbot command. Name your bot and select a unique username ending in "bot". Copy the HTTP API token provided by BotFather and paste it when creating a bot in My Bots or Bot Studio.',
    },
    {
      q: 'How does the Broadcast Audience Targeting work?',
      a: 'In Broadcast Manager select one or more of your bots, choose audience filters (language, blocked status, join date), compose the message with optional media, then schedule or send immediately. Delivery speed is controlled by your plan limits.',
    },
    {
      q: 'Why did my bot stop running?',
      a: 'Bots stop when points run out, when you manually stop them, or after a critical runtime error. Check Notifications and the bot Errors panel in Bot Studio. Top up points under Plans & Billing to resume.',
    },
    {
      q: 'Can I transfer a bot to another account?',
      a: 'Yes. Open My Bots, choose Transfer, enter the recipient email, and confirm. The other user must accept within the expiry window shown on the transfer card.',
    },
    {
      q: 'How do support tickets work?',
      a: 'Open Support → Open Ticket, pick a department, subject and message. Our team replies in the same ticket thread. You can reply, close, or reopen any of your tickets at any time.',
    },
  ];

  const filteredFaqs = faqs.filter(
    (f) =>
      f.q.toLowerCase().includes(faqSearch.toLowerCase()) ||
      f.a.toLowerCase().includes(faqSearch.toLowerCase())
  );

  return (
    <div className="space-y-6 pb-12 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight flex items-center gap-2">
          <span>Help & Support Center</span>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-800">
            24/7 Enterprise Assistance
          </span>
        </h1>
        <p className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 mt-1 font-medium">
          Comprehensive project documentation, Python Telebot guides, broadcast orchestration manuals, and direct technical support.
        </p>
      </div>

      {/* Sub Tabs Switcher */}
            {/* Sub-tabs removed: Help page = docs only, Support page = tickets only */}
{/* TAB 1: HELP & DOCUMENTATION */}
      {mode === 'help' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="glass-panel p-5 rounded-2xl space-y-3 border border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-blue-100 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 flex items-center justify-center font-bold">
                  1
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900 dark:text-white">Bot Creation & @BotFather Setup</h3>
                  <span className="text-[11px] text-slate-400">Telegram Token Integration</span>
                </div>
              </div>
              <ol className="text-xs text-slate-700 dark:text-slate-300 space-y-1.5 list-decimal list-inside leading-relaxed font-medium">
                <li>
                  Message <strong>@BotFather</strong> on Telegram.
                </li>
                <li>
                  Send command{' '}
                  <code className="px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 font-mono font-semibold">/newbot</code>.
                </li>
                <li>
                  Assign a display name and username ending in{' '}
                  <code className="px-1 py-0.5 rounded bg-slate-200 dark:bg-slate-800 font-mono text-[11px]">_bot</code>.
                </li>
                <li>Copy the HTTP API Token into BOT MATRIX to deploy immediately.</li>
              </ol>
            </div>

            <div className="glass-panel p-5 rounded-2xl space-y-3 border border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-indigo-100 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center font-bold">
                  2
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900 dark:text-white">Bot Studio & Command Scripting</h3>
                  <span className="text-[11px] text-slate-400">Python Telebot Code Engine</span>
                </div>
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-medium">
                In Bot Studio, click any command to launch the full-screen editor. Code auto-saves with database persistence. Use{' '}
                <code className="px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 font-mono text-[11px]">message.chat.id</code> and{' '}
                <code className="px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-800 font-mono text-[11px]">bot.send_message</code> for rich
                responses.
              </p>
            </div>

            <div className="glass-panel p-5 rounded-2xl space-y-3 border border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center font-bold">
                  3
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900 dark:text-white">Broadcast Engine</h3>
                  <span className="text-[11px] text-slate-400">Audience targeting & delivery</span>
                </div>
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-medium">
                Select bots, filter audience by language or status, attach media, then send or schedule. Speed and volume depend on your plan.
              </p>
            </div>

            <div className="glass-panel p-5 rounded-2xl space-y-3 border border-slate-200 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-xl bg-amber-100 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center font-bold">
                  4
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900 dark:text-white">Plans, Points & Billing</h3>
                  <span className="text-[11px] text-slate-400">Usage & upgrades</span>
                </div>
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-medium">
                Each bot action spends points. When points hit zero, bots pause automatically. Upgrade or top up under Plans & Billing.
              </p>
            </div>
          </div>

          <div className="glass-panel p-5 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-blue-500" />
                Frequently Asked Questions
              </h3>
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={faqSearch}
                  onChange={(e) => setFaqSearch(e.target.value)}
                  placeholder="Search FAQ..."
                  className="pl-8 pr-3 py-1.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-blue-500/30 w-48"
                />
              </div>
            </div>
            <div className="space-y-2">
              {filteredFaqs.map((faq, idx) => {
                const isOpen = openFaqIndex === idx;
                return (
                  <div key={idx} className="rounded-xl border border-slate-200 dark:border-slate-800 p-3">
                    <button
                      type="button"
                      onClick={() => setOpenFaqIndex(isOpen ? null : idx)}
                      className="w-full flex items-center justify-between gap-2 text-left cursor-pointer"
                    >
                      <span className="text-xs font-bold text-slate-900 dark:text-white">{faq.q}</span>
                      {isOpen ? (
                        <ChevronUp className="w-4 h-4 text-blue-500 shrink-0" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
                      )}
                    </button>
                    {isOpen && (
                      <p className="text-xs text-slate-600 dark:text-slate-400 mt-2 leading-relaxed pl-1 font-medium">{faq.a}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: SUPPORT DESK — NinzaHost-style ticket system */}
      {mode === 'support' && (
        <div className="space-y-5">
          {/* Toolbar */}
          {view !== 'detail' && (
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <LifeBuoy className="w-5 h-5 text-blue-500" />
                  {view === 'open' ? 'Open a New Ticket' : 'My Support Tickets'}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {view === 'open'
                    ? 'Describe your issue. Our team will reply in this same thread.'
                    : 'Track, reply, and close your support conversations.'}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {view === 'open' ? (
                  <button
                    type="button"
                    onClick={() => setView('list')}
                    className="px-3 py-2 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center gap-1.5 cursor-pointer"
                  >
                    <ArrowLeft className="w-3.5 h-3.5" />
                    My Tickets
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setView('open');
                      setFormError(null);
                      setFormSuccess(null);
                    }}
                    className="px-3 py-2 rounded-xl text-xs font-bold bg-blue-600 text-white shadow-sm shadow-blue-500/20 hover:bg-blue-700 flex items-center gap-1.5 cursor-pointer"
                  >
                    <Send className="w-3.5 h-3.5" />
                    Open Ticket
                  </button>
                )}
                {view === 'list' && (
                  <button
                    type="button"
                    onClick={loadTickets}
                    className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 cursor-pointer"
                    title="Refresh"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${ticketsLoading ? 'animate-spin' : ''}`} />
                  </button>
                )}
              </div>
            </div>
          )}

          {/* LIST VIEW */}
          {view === 'list' && (
            <div className="glass-panel rounded-3xl border border-slate-200 dark:border-slate-800 overflow-hidden">
              {ticketsLoading && ticketsList.length === 0 ? (
                <div className="p-10 text-center text-xs text-slate-500">Loading tickets…</div>
              ) : ticketsList.length === 0 ? (
                <div className="p-10 text-center space-y-3">
                  <div className="w-14 h-14 mx-auto rounded-2xl bg-blue-50 dark:bg-blue-950/40 flex items-center justify-center">
                    <LifeBuoy className="w-7 h-7 text-blue-500" />
                  </div>
                  <p className="text-sm font-bold text-slate-900 dark:text-white">No tickets yet</p>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    Open a ticket when you need help with bots, billing, broadcasts, or account issues.
                  </p>
                  <button
                    type="button"
                    onClick={() => setView('open')}
                    className="mt-2 px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                  >
                    Open your first ticket
                  </button>
                </div>
              ) : (
                <div className="divide-y divide-slate-200 dark:divide-slate-800">
                  {ticketsList.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => openDetail(t.id)}
                      className="w-full text-left px-5 py-4 hover:bg-slate-50 dark:hover:bg-slate-900/40 transition cursor-pointer flex flex-col sm:flex-row sm:items-center gap-3 justify-between"
                    >
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="px-2 py-0.5 rounded font-mono font-bold text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                            {t.id}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${statusStyle(t.status)}`}>
                            {statusLabel(t.status)}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${priorityStyle(t.priority)}`}>
                            {t.priority || 'Normal'}
                          </span>
                        </div>
                        <p className="text-sm font-bold text-slate-900 dark:text-white truncate">
                          {t.subject || t.category || 'Support request'}
                        </p>
                        <p className="text-xs text-slate-500 line-clamp-1">{t.message}</p>
                        <p className="text-[10px] text-slate-400">
                          {t.department || t.category || 'General'}
                          {t.updatedAt || t.createdAt
                            ? ` · ${new Date(t.updatedAt || t.createdAt).toLocaleString()}`
                            : ''}
                        </p>
                      </div>
                      <ArrowRight className="w-4 h-4 text-slate-400 shrink-0 hidden sm:block" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* OPEN TICKET FORM */}
          {view === 'open' && (
            <form onSubmit={handleCreateTicket} className="glass-panel p-6 rounded-3xl border border-slate-200 dark:border-slate-800 space-y-4">
              {formError && (
                <div className="p-3 rounded-2xl bg-red-50 dark:bg-red-950/50 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-xs font-semibold">
                  {formError}
                </div>
              )}
              {formSuccess && (
                <div className="p-3 rounded-2xl bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-300 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs font-semibold flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  Ticket created successfully — ID: {formSuccess}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
                    Department
                  </label>
                  <select
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-blue-500/30"
                  >
                    {DEPARTMENTS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-[11px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
                    Priority
                  </label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-blue-500/30"
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
                  Subject
                </label>
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="Brief summary of your issue"
                  maxLength={120}
                  className="w-full px-3 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wide">
                  Message
                </label>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Describe the problem, steps to reproduce, bot username, error text…"
                  rows={6}
                  maxLength={4000}
                  className="w-full px-3 py-2.5 rounded-xl text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 outline-none focus:ring-2 focus:ring-blue-500/30 resize-y min-h-[140px]"
                />
                <p className="text-[10px] text-slate-400 text-right">{message.length}/4000</p>
              </div>

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setView('list')}
                  className="px-4 py-2.5 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2.5 rounded-xl text-xs font-bold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 flex items-center gap-2 cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" />
                  {isSubmitting ? 'Submitting…' : 'Submit Ticket'}
                </button>
              </div>
            </form>
          )}

          {/* DETAIL / CONVERSATION VIEW */}
          {view === 'detail' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={() => {
                    setView('list');
                    setTicketDetail(null);
                    setSelectedId(null);
                  }}
                  className="px-3 py-2 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 flex items-center gap-1.5 cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  All tickets
                </button>
                {ticketDetail && (
                  <div className="flex items-center gap-2">
                    {(ticketDetail.status || '').toLowerCase() !== 'closed' ? (
                      <button
                        type="button"
                        onClick={handleClose}
                        className="px-3 py-2 rounded-xl text-xs font-bold bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:opacity-90 cursor-pointer"
                      >
                        Close ticket
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={handleReopen}
                        className="px-3 py-2 rounded-xl text-xs font-bold bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
                      >
                        Reopen ticket
                      </button>
                    )}
                  </div>
                )}
              </div>

              {actionError && (
                <div className="p-3 rounded-2xl bg-red-50 dark:bg-red-950/50 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 text-xs font-semibold">
                  {actionError}
                </div>
              )}

              {detailLoading || !ticketDetail ? (
                <div className="glass-panel p-10 rounded-3xl border border-slate-200 dark:border-slate-800 text-center text-xs text-slate-500">
                  {detailLoading ? 'Loading conversation…' : 'Ticket not found.'}
                </div>
              ) : (
                <>
                  {/* Meta card */}
                  <div className="glass-panel p-5 rounded-3xl border border-slate-200 dark:border-slate-800 space-y-3">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="px-2 py-0.5 rounded font-mono font-bold text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                            {ticketDetail.id}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${statusStyle(ticketDetail.status)}`}>
                            {statusLabel(ticketDetail.status)}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${priorityStyle(ticketDetail.priority)}`}>
                            {ticketDetail.priority || 'Normal'}
                          </span>
                        </div>
                        <h3 className="text-base font-bold text-slate-900 dark:text-white">
                          {ticketDetail.subject || ticketDetail.category || 'Support request'}
                        </h3>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
                      <div>
                        <p className="text-slate-400 font-bold uppercase tracking-wide">Department</p>
                        <p className="text-slate-800 dark:text-slate-200 font-semibold">
                          {ticketDetail.department || ticketDetail.category || 'General'}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-400 font-bold uppercase tracking-wide">Opened</p>
                        <p className="text-slate-800 dark:text-slate-200 font-semibold">
                          {ticketDetail.createdAt ? new Date(ticketDetail.createdAt).toLocaleString() : '—'}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-400 font-bold uppercase tracking-wide">Updated</p>
                        <p className="text-slate-800 dark:text-slate-200 font-semibold">
                          {ticketDetail.updatedAt ? new Date(ticketDetail.updatedAt).toLocaleString() : '—'}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-400 font-bold uppercase tracking-wide">Replies</p>
                        <p className="text-slate-800 dark:text-slate-200 font-semibold">
                          {(ticketDetail.replies || []).length}
                        </p>
                      </div>
                    </div>
                  </div>

                  <SupportChat
                    perspective="user"
                    title={ticketDetail.subject || ticketDetail.category || 'Support'}
                    subtitle={`${ticketDetail.id || ''} · ${ticketDetail.department || ticketDetail.category || 'General'}`}
                    status={statusLabel(ticketDetail.status)}
                    userName={ticketDetail.name || 'You'}
                    adminName="Admin"
                    closed={(ticketDetail.status || '').toLowerCase() === 'closed'}
                    sending={replySending}
                    input={replyText}
                    onInput={notifyTyping}
                    peerTyping={peerTyping}
                    peerTypingLabel="Admin is typing"
                    onSend={handleReply}
                    closedHint="This ticket is closed. Neither Admin nor User can reply until it is reopened."
                    messages={[
                      {
                        id: 'orig',
                        message: ticketDetail.message || '',
                        isStaff: false,
                        authorName: ticketDetail.name || 'You',
                        createdAt: ticketDetail.createdAt,
                        deliveredAt: ticketDetail.createdAt,
                        seenAt: ticketDetail.createdAt,
                      },
                      ...((ticketDetail.replies || []).map((r: any) => ({
                        id: r.id,
                        message: r.message,
                        isStaff: !!r.isStaff,
                        authorName: r.authorName,
                        createdAt: r.createdAt,
                        deliveredAt: r.deliveredAt || r.createdAt,
                        seenAt: r.seenAt,
                      }))),
                    ]}
                  />

                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: CLUSTER & API STATUS */}
      {false && <LiveStatus />}
    </div>
  );
};
