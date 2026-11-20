import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Search,
  Users,
  ShieldAlert,
  ShieldCheck,
  Ban,
  CheckCircle2,
  Clock,
  MessageSquare,
  Send,
  UserX,
  UserCheck,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ExternalLink,
  MoreVertical,
  Download,
  FileText,
  User,
  X,
  Sparkles,
  ArrowRight,
  Layers,
} from 'lucide-react';
import { BotItem, BotChatUser } from '../types';
import { AudienceListSkeleton } from './SkeletonScreen';
import { apiService } from '../services/apiService';

interface BotChatsViewProps {
  bot: BotItem;
  onUpdateBot: (updated: BotItem) => void;
  onShowToast: (msg: string) => void;
}

const fmtTime = (s?: string) => {
  if (!s) return '—';
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString();
};

// Helper to seed scalable high-volume audience records for pagination testing
const generateExpandedAudience = (baseUsers: BotChatUser[]): BotChatUser[] => {
  // Real data only — never invent audience members
  return Array.isArray(baseUsers) ? baseUsers : [];
};

export const BotChatsView: React.FC<BotChatsViewProps> = ({
  bot,
  onUpdateBot,
  onShowToast,
}) => {
  // Live audience straight from the server (paged + searched on the server, refreshed every few seconds)
  const [chatUsers, setChatUsers] = useState<BotChatUser[]>([]);
  const [serverTotal, setServerTotal] = useState(0);
  const [counts, setCounts] = useState({ all: 0, active: 0, blocked: 0, leftBot: 0 });
  const [loaded, setLoaded] = useState(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'All' | 'Active' | 'Blocked' | 'Left'>('All');
  const [selectedUser, setSelectedUser] = useState<BotChatUser | null>(null);
  const [quickReplyText, setQuickReplyText] = useState('');

  // Pagination states
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [jumpPageInput, setJumpPageInput] = useState<string>('');
  const [isPageTransitioning, setIsPageTransitioning] = useState<boolean>(false);

  // Export Modal State

  const loadUsers = useCallback(async () => {
    try {
      const r = await apiService.getAudienceUsers(bot.id, {
        page: currentPage, limit: pageSize, search: searchQuery.trim(),
        filter: filterType === 'All' ? 'all' : filterType.toLowerCase(),
      });
      setChatUsers(r.users || []);
      setServerTotal(r.total || 0);
      if (r.counts) setCounts(r.counts);
      setLoaded(true);
      setSelectedUser((cur) => (cur ? (r.users || []).find((u) => u.id === cur.id) || cur : cur));
    } catch { /* keep what is on screen */ }
  }, [bot.id, currentPage, pageSize, searchQuery, filterType]);

  useEffect(() => {
    loadUsers();
    const t = setInterval(() => { if (!document.hidden) loadUsers(); }, 4000);
    const h = () => loadUsers();
    window.addEventListener('bm_refresh', h);
    return () => { clearInterval(t); window.removeEventListener('bm_refresh', h); };
  }, [loadUsers]);

  useEffect(() => { setCurrentPage(1); }, [searchQuery, filterType, pageSize]);

  // Toggle block / unblock for user (saved on the server)
  const handleToggleBlock = async (userId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const target = chatUsers.find((u) => u.id === userId);
    if (!target) return;
    try {
      const r = await apiService.toggleBlockUser(bot.id, target.telegramId);
      onShowToast(r.isBlocked ? `Blocked ${target.name} (${target.username})` : `Unblocked ${target.name} (${target.username})`);
      loadUsers();
    } catch (err: any) {
      onShowToast(err?.message || 'Could not change the block state');
    }
  };

  const filteredUsers = chatUsers;

  const totalFilteredCount = serverTotal;
  const totalPages = Math.max(1, Math.ceil(totalFilteredCount / pageSize));
  const safeCurrentPage = Math.min(Math.max(1, currentPage), totalPages);

  const startIndex = (safeCurrentPage - 1) * pageSize;
  const endIndex = Math.min(startIndex + chatUsers.length, totalFilteredCount);
  const paginatedUsers = chatUsers;

  const handlePageChange = (targetPage: number) => {
    const valid = Math.min(Math.max(1, targetPage), totalPages);
    if (valid === safeCurrentPage) return;
    setIsPageTransitioning(true);
    setCurrentPage(valid);
    setTimeout(() => {
      setIsPageTransitioning(false);
    }, 220);
  };

  const handleJumpToPage = (e: React.FormEvent) => {
    e.preventDefault();
    const p = parseInt(jumpPageInput.trim(), 10);
    if (!isNaN(p) && p >= 1 && p <= totalPages) {
      handlePageChange(p);
      setJumpPageInput('');
    } else {
      onShowToast(`Please enter a valid page number between 1 and ${totalPages}`);
    }
  };

  const handlePageSizeChange = (newSize: number) => {
    setIsPageTransitioning(true);
    setPageSize(newSize);
    setCurrentPage(1);
    onShowToast(`Showing ${newSize} users per page`);
    setTimeout(() => {
      setIsPageTransitioning(false);
    }, 220);
  };

  const totalCount = counts.all;
  const activeCount = counts.active;
  const blockedCount = counts.blocked;

  const handleSendQuickReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickReplyText.trim() || !selectedUser) return;
    const text = quickReplyText.trim();
    try {
      await apiService.sendChatMessage(bot.id, selectedUser.telegramId, text);
      onShowToast(`Sent to ${selectedUser.name || selectedUser.username || selectedUser.telegramId}`);
      setQuickReplyText('');
    } catch (err: any) {
      onShowToast(err?.response?.data?.error || err?.message || 'Failed to send message');
    }
  };

  return (
    <div className="space-y-4">
      {/* Top Header Card */}
      <div className="glass-panel p-5 rounded-3xl space-y-4 border border-slate-200 dark:border-slate-800">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h2 className="text-lg font-black text-slate-900 dark:text-white flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-blue-600" />
              <span>Bot Telegram Chats & Audience</span>
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Everyone who started your bot, saved automatically. Import or export users from Manage → Users.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {/* Quick stats pills */}
            <span className="px-3 py-1 rounded-xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 text-xs font-bold border border-blue-200 dark:border-blue-900/40">
              Total: {totalCount}
            </span>
            <span className="px-3 py-1 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 text-xs font-bold border border-emerald-200 dark:border-emerald-900/40">
              Active: {activeCount}
            </span>
            <span className="px-3 py-1 rounded-xl bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 text-xs font-bold border border-rose-200 dark:border-rose-900/40">
              Blocked: {blockedCount}
            </span>
          </div>
        </div>

        {/* Search Bar & Filter Tabs */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          {/* Search Box */}
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search users by name, username, or Telegram ID..."
              className="w-full pl-10 pr-4 py-2.5 rounded-2xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 font-medium"
            />
          </div>

          {/* Filter Pills: All, Active, Blocked */}
          <div className="flex items-center gap-1.5 p-1 rounded-2xl bg-slate-100 dark:bg-slate-800/80 shrink-0">
            {(['All', 'Active', 'Blocked', 'Left'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setFilterType(tab)}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  filterType === tab
                    ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-300 shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {tab === 'Left' ? 'Left bot' : tab}
                {tab === 'All' && ` (${totalCount})`}
                {tab === 'Active' && ` (${activeCount})`}
                {tab === 'Blocked' && ` (${blockedCount})`}
                {tab === 'Left' && ` (${counts.leftBot})`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Content Layout: User List + Optional Detail/Reply Drawer */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Users List Column */}
        <div className={selectedUser ? 'lg:col-span-2 space-y-3' : 'lg:col-span-3 space-y-3'}>
          {/* Quick Telemetry Bar above the list */}
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-slate-500 font-medium">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 font-bold border border-blue-200/80 dark:border-blue-900/40">
                <Users className="w-3.5 h-3.5 text-blue-500" />
                <span>Total Filtered: {totalFilteredCount.toLocaleString()}</span>
              </span>
              <span>
                Showing {totalFilteredCount > 0 ? startIndex + 1 : 0}–{endIndex} of {totalFilteredCount.toLocaleString()}
              </span>
            </div>

            {/* Page Size Picker */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-slate-400">Rows per page</span>
              <div className="inline-flex rounded-lg border border-slate-200 dark:border-slate-700 p-0.5 bg-slate-100 dark:bg-slate-800">
                {[10, 25, 50, 100, 500, 1000].map((sz) => (
                  <button
                    key={sz}
                    type="button"
                    onClick={() => handlePageSizeChange(sz)}
                    className={`px-2 py-0.5 text-[11px] font-bold rounded-md transition-colors ${
                      pageSize === sz
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                    }`}
                  >
                    {sz}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {filteredUsers.length === 0 ? (
            <div className="glass-panel p-10 rounded-3xl text-center space-y-2 border border-slate-200 dark:border-slate-800">
              <UserX className="w-8 h-8 text-slate-400 mx-auto" />
              <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">
                No Telegram users found
              </h3>
              <p className="text-xs text-slate-500">
                Try a different search query or change the status filter.
              </p>
            </div>
          ) : isPageTransitioning ? (
            <AudienceListSkeleton rows={Math.min(pageSize, 8)} />
          ) : (
            <div className="space-y-2.5">
              {paginatedUsers.map((usr) => {
                const isSelected = selectedUser?.id === usr.id;
                return (
                  <motion.div
                    key={usr.id}
                    layout
                    whileHover={{ scale: 1.004 }}
                    onClick={() => setSelectedUser(usr)}
                    className={`p-3.5 sm:p-4 rounded-2xl border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs ${
                      isSelected
                        ? 'bg-blue-50/80 dark:bg-blue-950/40 border-blue-500 ring-1 ring-blue-500/30'
                        : usr.isBlocked
                        ? 'bg-rose-50/30 dark:bg-rose-950/20 border-rose-200/80 dark:border-rose-900/40'
                        : 'bg-white dark:bg-slate-800/90 border-slate-200 dark:border-slate-700/80 hover:border-blue-400'
                    }`}
                  >
                    {/* Left: User Telegram Profile Photo or Avatar */}
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div
                        className={`w-11 h-11 rounded-full bg-gradient-to-tr ${
                          usr.avatarColor || 'from-blue-600 to-indigo-600'
                        } text-white flex items-center justify-center font-black text-sm shrink-0 shadow-sm relative overflow-hidden border border-slate-200 dark:border-slate-700`}
                      >
                        {usr.photoUrl ? (
                          <img
                            src={usr.photoUrl}
                            alt={usr.name}
                            loading="lazy"
                            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                            className="w-full h-full object-cover rounded-full absolute inset-0"
                          />
                        ) : null}
                        <span className="font-black">{(usr.name || '?').trim().charAt(0).toUpperCase()}</span>
                        {usr.isBlocked && (
                          <span
                            title="User is blocked"
                            className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full bg-rose-600 text-white flex items-center justify-center text-[10px]"
                          >
                            ✕
                          </span>
                        )}
                      </div>

                      {/* Name, Username, Date & Time, Message */}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="font-bold text-xs sm:text-sm text-slate-900 dark:text-white truncate">
                            {usr.name}
                          </h4>
                          {usr.isBlocked ? (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border border-rose-300 dark:border-rose-800">
                              Blocked
                            </span>
                          ) : usr.botBlocked ? (
                            <span title="The user blocked or removed the bot" className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-800">
                              Left bot
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800">
                              Active
                            </span>
                          )}
                        </div>

                        {/* Username below name */}
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs font-mono font-semibold text-blue-600 dark:text-blue-400">
                            {usr.username}
                          </span>
                          <span className="text-slate-400 text-xs">•</span>
                          <span className="text-[11px] font-mono text-slate-500">
                            ID: {usr.telegramId}
                          </span>
                          {usr.languageCode ? (
                            <>
                              <span className="text-slate-400 text-xs">•</span>
                              <span title="Telegram language code" className="px-1.5 py-0.5 rounded-md text-[10px] font-mono font-bold uppercase bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                                {usr.languageCode}
                              </span>
                            </>
                          ) : null}
                        </div>

                        {/* Date & Time below username */}
                        <div className="flex items-center gap-1.5 mt-1 text-[11px] text-slate-500">
                          <Clock className="w-3 h-3 text-slate-400 shrink-0" />
                          <span>{fmtTime(usr.lastActive)}</span>
                          {usr.lastMessage && (
                            <>
                              <span className="text-slate-300">•</span>
                              <span className="truncate max-w-[200px] sm:max-w-[340px] text-slate-600 dark:text-slate-300 italic font-medium">
                                "{usr.lastMessage}"
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Side: Block / Unblock Action Button */}
                    <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
                      <button
                        type="button"
                        onClick={(e) => handleToggleBlock(usr.id, e)}
                        className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-xs ${
                          usr.isBlocked
                            ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-emerald-500/20'
                            : 'bg-rose-100 hover:bg-rose-200 text-rose-700 dark:bg-rose-950/50 dark:hover:bg-rose-900/60 dark:text-rose-300 border border-rose-300 dark:border-rose-800'
                        }`}
                        title={usr.isBlocked ? 'Unblock user' : 'Block user'}
                      >
                        {usr.isBlocked ? (
                          <>
                            <UserCheck className="w-3.5 h-3.5" />
                            <span>Unblock</span>
                          </>
                        ) : (
                          <>
                            <Ban className="w-3.5 h-3.5" />
                            <span>Block</span>
                          </>
                        )}
                      </button>

                      <a
                        href={`https://t.me/${usr.username.replace('@', '')}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="p-2 rounded-xl bg-slate-100 dark:bg-slate-700/80 text-slate-600 dark:text-slate-300 hover:text-blue-600 transition-colors"
                        title="Open chat on Telegram"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Advanced Pagination Toolbar */}
          {totalPages > 1 && (
            <div className="glass-panel p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-xs">
              {/* Left: Page range and navigation */}
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => handlePageChange(1)}
                  disabled={safeCurrentPage === 1}
                  className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="First Page"
                >
                  <ChevronsLeft className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => handlePageChange(safeCurrentPage - 1)}
                  disabled={safeCurrentPage === 1}
                  className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="Previous Page"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>

                {/* Windowed Page Numbers */}
                <div className="flex items-center gap-1 px-1">
                  {(() => {
                    const pages: (number | string)[] = [];
                    const maxButtons = 5;
                    let start = Math.max(1, safeCurrentPage - 2);
                    let end = Math.min(totalPages, start + maxButtons - 1);
                    if (end - start + 1 < maxButtons) {
                      start = Math.max(1, end - maxButtons + 1);
                    }

                    if (start > 1) {
                      pages.push(1);
                      if (start > 2) pages.push('...');
                    }
                    for (let p = start; p <= end; p++) {
                      pages.push(p);
                    }
                    if (end < totalPages) {
                      if (end < totalPages - 1) pages.push('...');
                      pages.push(totalPages);
                    }

                    return pages.map((item, idx) => {
                      if (typeof item === 'string') {
                        return (
                          <span key={`ellipsis-${idx}`} className="px-1 text-xs text-slate-400 font-mono">
                            •••
                          </span>
                        );
                      }
                      const isCurrent = item === safeCurrentPage;
                      return (
                        <button
                          key={`page-${item}`}
                          type="button"
                          onClick={() => handlePageChange(item)}
                          className={`min-w-8 h-8 px-2 rounded-lg text-xs font-bold transition-all ${
                            isCurrent
                              ? 'bg-blue-600 text-white shadow-sm shadow-blue-500/30'
                              : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                          }`}
                        >
                          {item}
                        </button>
                      );
                    });
                  })()}
                </div>

                <button
                  type="button"
                  onClick={() => handlePageChange(safeCurrentPage + 1)}
                  disabled={safeCurrentPage === totalPages}
                  className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="Next Page"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => handlePageChange(totalPages)}
                  disabled={safeCurrentPage === totalPages}
                  className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="Last Page"
                >
                  <ChevronsRight className="w-4 h-4" />
                </button>
              </div>

              {/* Right: Direct Page Jump Input */}
              <form onSubmit={handleJumpToPage} className="flex items-center gap-1.5 text-xs text-slate-500">
                <span>Jump to page</span>
                <input
                  type="number"
                  min={1}
                  max={totalPages}
                  value={jumpPageInput}
                  onChange={(e) => setJumpPageInput(e.target.value)}
                  placeholder={`${safeCurrentPage}/${totalPages}`}
                  className="w-16 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white text-xs font-mono text-center focus:outline-none focus:border-blue-500"
                />
                <button
                  type="submit"
                  className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-blue-600 hover:text-white dark:hover:bg-blue-600 text-slate-700 dark:text-slate-300 text-xs font-bold transition-colors cursor-pointer"
                >
                  Go
                </button>
              </form>
            </div>
          )}
        </div>

        {/* Selected User Details / Conversation Inspector Drawer */}
        {selectedUser && (
          <motion.div
            initial={{ opacity: 0, x: 15 }}
            animate={{ opacity: 1, x: 0 }}
            className="glass-panel p-5 rounded-3xl border border-slate-200 dark:border-slate-800 space-y-4 self-start"
          >
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                User Details
              </h3>
              <button
                type="button"
                onClick={() => setSelectedUser(null)}
                className="text-xs font-bold text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                Close
              </button>
            </div>

            <div className="space-y-1.5">
              <h4 className="font-bold text-sm text-slate-900 dark:text-white truncate">
                {selectedUser.name}
              </h4>
              <p className="font-mono text-xs text-blue-600 dark:text-blue-400 truncate">
                {selectedUser.username}
              </p>
              <p className="text-[11px] font-mono text-slate-500">
                Telegram ID {selectedUser.telegramId}
              </p>
            </div>

            <div className="p-3 rounded-2xl bg-slate-100 dark:bg-slate-800/80 text-xs space-y-1.5">
              <div className="flex justify-between text-slate-500">
                <span>Status</span>
                <span className={`font-bold ${selectedUser.isBlocked ? 'text-rose-600' : 'text-emerald-600'}`}>
                  {selectedUser.isBlocked ? 'Blocked' : 'Active'}
                </span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>Last Active</span>
                <span className="font-medium text-slate-700 dark:text-slate-300">
                  {fmtTime(selectedUser.lastActive)}
                </span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>First Seen</span>
                <span className="font-medium text-slate-700 dark:text-slate-300">{fmtTime(selectedUser.firstSeen)}</span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>Language</span>
                <span className="font-medium text-slate-700 dark:text-slate-300">{selectedUser.languageCode || '—'}</span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>Bot Access</span>
                <span className={`font-bold ${selectedUser.botBlocked ? 'text-amber-600' : 'text-emerald-600'}`}>{selectedUser.botBlocked ? 'User left / blocked the bot' : 'Reachable'}</span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>Total Messages</span>
                <span className="font-medium text-slate-700 dark:text-slate-300">
                  {selectedUser.messagesCount ?? 0}
                </span>
              </div>
            </div>

            {/* Block / Unblock in drawer */}
            <button
              type="button"
              onClick={(e) => handleToggleBlock(selectedUser.id, e)}
              className={`w-full py-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer ${
                selectedUser.isBlocked
                  ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
                  : 'bg-rose-600 hover:bg-rose-700 text-white'
              }`}
            >
              {selectedUser.isBlocked ? (
                <>
                  <UserCheck className="w-4 h-4" />
                  <span>Unblock This User</span>
                </>
              ) : (
                <>
                  <Ban className="w-4 h-4" />
                  <span>Block This User</span>
                </>
              )}
            </button>

            {/* Quick Telegram message simulator */}
            <form onSubmit={handleSendQuickReply} className="space-y-2 pt-2 border-t border-slate-200 dark:border-slate-800">
              <span className="text-[11px] font-bold text-slate-500 block">
                Send Direct Telegram Reply:
              </span>
              <textarea
                value={quickReplyText}
                onChange={(e) => setQuickReplyText(e.target.value)}
                placeholder="Type direct response message..."
                rows={2}
                className="w-full p-2.5 rounded-xl text-xs bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 resize-none font-medium"
              />
              <button
                type="submit"
                className="w-full py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send via Bot</span>
              </button>
            </form>
          </motion.div>
        )}
      </div>

    </div>
  );
};
