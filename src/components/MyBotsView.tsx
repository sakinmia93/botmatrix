import { apiService, apiErrorMessage } from '../services/apiService';
import { BotAvatar } from './BotAvatar';
import React, { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Bot,
  Plus,
  Search,
  Check,
  Copy,
  Trash2,
  Power,
  ExternalLink,
  Shield,
  Activity,
  Layers,
  X,
  Sparkles,
  Pin,
  Folder,
  FolderPlus,
  ArrowUpDown,
  Eye,
  EyeOff,
  Edit3,
  AlertTriangle,
  Play,
  Square,
  Users,
  Terminal,
  MoreVertical,
  ChevronLeft,
  ChevronRight,
  CheckSquare,
} from 'lucide-react';
import { BotItem, BotStatus } from '../types';
import { MyBotsCardsSkeleton } from './SkeletonScreen';

interface MyBotsViewProps {
  bots: BotItem[];
  onToggleStatus: (botId: string) => void;
  onMoveToRecycleBin: (botId: string) => void;
  onCreateBot: (newBot: Partial<BotItem>) => void | Promise<void>;
  searchQuery: string;
  onOpenEditor: (bot: BotItem) => void;
  onUpdateBot: (updated: BotItem) => void;
}

type SortCriterion = 'Name' | 'Status' | 'Users';

export const MyBotsView: React.FC<MyBotsViewProps> = ({
  bots,
  onToggleStatus,
  onMoveToRecycleBin,
  onCreateBot,
  searchQuery,
  onOpenEditor,
  onUpdateBot,
}) => {
  // Folder filter state
  const [selectedFolder, setSelectedFolder] = useState<string>('All');
  const [folders, setFolders] = useState<string[]>([]);

  React.useEffect(() => {
    let alive = true;
    apiService.getFolders().then((f) => {
      if (!alive) return;
      const list = Array.isArray(f) ? f.filter((n) => n && n !== 'All') : [];
      setFolders(list);
    }).catch(() => { if (alive) setFolders([]); });
    return () => { alive = false; };
  }, []);
  const [showNewFolderModal, setShowNewFolderModal] = useState(false);
  const [newFolderNameInput, setNewFolderNameInput] = useState('');

  // Status filter state (4 statuses: working, stopped, cloned, transferred)
  const [filterStatus, setFilterStatus] = useState<string>('All');
  const [localSearch, setLocalSearch] = useState<string>('');

  // Sort state: Name, Status, Users
  const [sortBy, setSortBy] = useState<SortCriterion>('Name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  // Transitioning state for skeleton loaders
  const [isTransitioning, setIsTransitioning] = useState(false);

  // Stepper lists for < and > navigation
  const statusList = ['All', 'working', 'stopped', 'cloned', 'transferred'];
  const allFolderOptions = ['All', ...folders];

  const triggerTransition = () => {
    setIsTransitioning(true);
    setTimeout(() => setIsTransitioning(false), 180);
  };

  const handleSelectFolder = (folderName: string) => {
    if (folderName === selectedFolder) return;
    triggerTransition();
    setSelectedFolder(folderName);
    setCurrentPage(1);
    setSelectedBotIds([]);
  };

  const handleSelectStatus = (statusName: string) => {
    if (statusName === filterStatus) return;
    triggerTransition();
    setFilterStatus(statusName);
    setCurrentPage(1);
    setSelectedBotIds([]);
  };

  const handlePrevFolder = () => {
    const currentIndex = allFolderOptions.indexOf(selectedFolder);
    const prevIndex = (currentIndex - 1 + allFolderOptions.length) % allFolderOptions.length;
    triggerTransition();
    setSelectedFolder(allFolderOptions[prevIndex]);
    setCurrentPage(1);
    setSelectedBotIds([]);
  };

  const handleNextFolder = () => {
    const currentIndex = allFolderOptions.indexOf(selectedFolder);
    const nextIndex = (currentIndex + 1) % allFolderOptions.length;
    triggerTransition();
    setSelectedFolder(allFolderOptions[nextIndex]);
    setCurrentPage(1);
    setSelectedBotIds([]);
  };

  const handlePrevStatus = () => {
    const currentIndex = statusList.findIndex(
      (s) => s.toLowerCase() === filterStatus.toLowerCase()
    );
    const prevIndex = (currentIndex - 1 + statusList.length) % statusList.length;
    triggerTransition();
    setFilterStatus(statusList[prevIndex]);
    setCurrentPage(1);
    setSelectedBotIds([]);
  };

  const handleNextStatus = () => {
    const currentIndex = statusList.findIndex(
      (s) => s.toLowerCase() === filterStatus.toLowerCase()
    );
    const nextIndex = (currentIndex + 1) % statusList.length;
    triggerTransition();
    setFilterStatus(statusList[nextIndex]);
    setCurrentPage(1);
    setSelectedBotIds([]);
  };

  // Pagination for scaling up to 20,000 bots smoothly
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(25);

  // Multi-selection: checkmarks only appear after long-press (mobile-style)
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressTriggered = useRef(false);
  const LONG_PRESS_MS = 480;

  const clearSelection = useCallback(() => {
    setSelectedBotIds([]);
    setSelectionMode(false);
  }, []);

  const enterSelectionWith = useCallback((botId: string) => {
    setSelectionMode(true);
    setSelectedBotIds((prev) => (prev.includes(botId) ? prev : [...prev, botId]));
  }, []);

  const handleToggleSelectBot = (botId: string) => {
    setSelectedBotIds((prev) => {
      const next = prev.includes(botId) ? prev.filter((id) => id !== botId) : [...prev, botId];
      if (next.length === 0) setSelectionMode(false);
      else setSelectionMode(true);
      return next;
    });
  };

  const onCardPointerDown = (botId: string) => {
    longPressTriggered.current = false;
    if (longPressTimer.current) clearTimeout(longPressTimer.current);
    longPressTimer.current = setTimeout(() => {
      longPressTriggered.current = true;
      enterSelectionWith(botId);
    }, LONG_PRESS_MS);
  };

  const onCardPointerUp = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  const handleBulkStart = () => {
    selectedBotIds.forEach((id) => {
      const b = bots.find((x) => x.id === id);
      if (b && b.status !== 'working') onToggleStatus(id);
    });
    showToast(`Started ${selectedBotIds.length} bot${selectedBotIds.length > 1 ? 's' : ''}`);
    clearSelection();
  };

  const handleBulkStop = () => {
    selectedBotIds.forEach((id) => {
      const b = bots.find((x) => x.id === id);
      if (b && b.status === 'working') onToggleStatus(id);
    });
    showToast(`Stopped ${selectedBotIds.length} bot${selectedBotIds.length > 1 ? 's' : ''}`);
    clearSelection();
  };

  const handleBulkDelete = () => {
    selectedBotIds.forEach((id) => onMoveToRecycleBin(id));
    showToast(`Moved ${selectedBotIds.length} bot${selectedBotIds.length > 1 ? 's' : ''} to Recycle Bin`);
    clearSelection();
  };

  const handleBulkMoveToFolder = async (folderName: string) => {
    if (!folderName || selectedBotIds.length === 0) return;
    const count = selectedBotIds.length;
    try {
      await Promise.all(
        selectedBotIds.map(async (id) => {
          const b = bots.find((x) => x.id === id);
          if (!b) return;
          const updated = await apiService.updateBot({ id, folder: folderName });
          onUpdateBot({ ...b, ...updated, folder: folderName });
        })
      );
      showToast(`Moved ${count} bot${count > 1 ? 's' : ''} to "${folderName}"`);
    } catch {
      showToast('Could not move bots to folder');
    }
    clearSelection();
  };

  // Hidden/Masked bot ID state (Default is hidden, click reveals)
  const [revealedIds, setRevealedIds] = useState<Record<string, boolean>>({});

  // Confirmation modal state for Start, Stop, Delete
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    actionLabel: string;
    isDanger: boolean;
    onConfirm: () => void;
  } | null>(null);

  // Create Bot Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newBotName, setNewBotName] = useState('');
  const [newBotUsername, setNewBotUsername] = useState('');
  const [newBotToken, setNewBotToken] = useState('');
  const [newBotFolder, setNewBotFolder] = useState('');
  const [createError, setCreateError] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Toast / Copy notification
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 2400);
  };

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    showToast(`Copied ${label} to clipboard`);
  };

  const toggleRevealId = (botId: string) => {
    setRevealedIds((prev) => ({ ...prev, [botId]: !prev[botId] }));
  };

  // Toggle Pinned
  const handleTogglePin = (bot: BotItem, e: React.MouseEvent) => {
    e.stopPropagation();
    onUpdateBot({ ...bot, isPinned: !bot.isPinned });
    showToast(bot.isPinned ? `Unpinned ${bot.name}` : `Pinned ${bot.name} to top`);
  };

  // Action confirmations
  const handlePromptToggleStatus = (bot: BotItem, e: React.MouseEvent) => {
    e.stopPropagation();
    const isWorking = bot.status === 'working';
    const action = isWorking ? 'Stop' : 'Start';
    setConfirmModal({
      isOpen: true,
      title: `${action} ${bot.name}?`,
      message: isWorking
        ? `Are you sure you want to stop ${bot.name} (${bot.username})? Polling and webhook traffic will be paused.`
        : `Are you sure you want to start ${bot.name} (${bot.username})? Commands and message responders will go live.`,
      actionLabel: action,
      isDanger: isWorking,
      onConfirm: () => {
        onToggleStatus(bot.id);
        setConfirmModal(null);
        showToast(`Bot ${bot.name} is now ${isWorking ? 'stopped' : 'working'}`);
      },
    });
  };

  const handlePromptDelete = (bot: BotItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setConfirmModal({
      isOpen: true,
      title: `Move ${bot.name} to Recycle Bin?`,
      message: `Are you sure you want to remove ${bot.name} (${bot.username}) from active bots? You can restore it later from the Recycle Bin.`,
      actionLabel: 'Delete to Recycle Bin',
      isDanger: true,
      onConfirm: () => {
        onMoveToRecycleBin(bot.id);
        setConfirmModal(null);
        showToast(`Moved ${bot.name} to Recycle Bin`);
      },
    });
  };

  const handleCreateFolder = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFolderNameInput.trim()) return;
    const name = newFolderNameInput.trim();
    apiService.addFolder(name).then((list) => {
      if (Array.isArray(list)) {
        setFolders(list.filter((n) => n && n !== 'All'));
      } else if (!folders.includes(name)) {
        setFolders((prev) => [...prev, name]);
      }
      setSelectedFolder(name);
      setNewFolderNameInput('');
      setShowNewFolderModal(false);
      showToast(`Created folder "${name}"`);
    }).catch(() => {
      if (!folders.includes(name)) setFolders((prev) => [...prev, name]);
      setSelectedFolder(name);
      setNewFolderNameInput('');
      setShowNewFolderModal(false);
      showToast(`Created folder "${name}"`);
    });
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBotToken.trim() || isCreating) return;
    const tokenClean = newBotToken.trim().replace(/\s+/g, '');
    setCreateError('');
    setIsCreating(true);
    const finishOk = () => {
      setNewBotName('');
      setNewBotUsername('');
      setNewBotToken('');
      setNewBotFolder('');
      setShowCreateModal(false);
      showToast('Bot connected successfully');
    };
    try {
      await onCreateBot({
        token: tokenClean,
        name: newBotName.trim() || undefined,
        username: newBotUsername.trim() || undefined,
        folder: newBotFolder || '',
      });
      finishOk();
    } catch (err: any) {
      // Server may have created the bot even if the response timed out — verify before showing failure
      try {
        const list = await apiService.getBots();
        const numeric = tokenClean.split(':')[0];
        const found = Array.isArray(list)
          ? list.find(
              (b) =>
                (b.botNumericId && String(b.botNumericId) === numeric) ||
                (b.tokenMasked && numeric && String(b.tokenMasked).endsWith(String(numeric).slice(-4))),
            )
          : null;
        if (found) {
          finishOk();
          return;
        }
      } catch {}
      setCreateError(
        apiErrorMessage(
          err,
          err?.code === 'ECONNABORTED'
            ? 'The request took too long. If the bot appears in the list, it was added successfully.'
            : err?.message === 'Network Error'
              ? 'Cannot reach the server. Check your connection.'
              : 'Could not add this bot. Check the token and try again.',
        ),
      );
    } finally {
      setIsCreating(false);
    }
  };

  const effectiveSearch = searchQuery || localSearch;

  // Filter bots
  const activeBots = bots.filter((b) => !b.inRecycleBin);

  const filteredBots = activeBots.filter((b) => {
    const matchesSearch =
      b.name.toLowerCase().includes(effectiveSearch.toLowerCase()) ||
      b.username.toLowerCase().includes(effectiveSearch.toLowerCase()) ||
      b.botNumericId.includes(effectiveSearch);

    const matchesStatus =
      filterStatus === 'All' || b.status.toLowerCase() === filterStatus.toLowerCase();

    const matchesFolder =
      selectedFolder === 'All' || (b.folder || 'Main Bots') === selectedFolder;

    return matchesSearch && matchesStatus && matchesFolder;
  });

  // Sort bots
  const sortedBots = [...filteredBots].sort((a, b) => {
    if (sortBy === 'Name') {
      const cmp = a.name.localeCompare(b.name);
      return sortOrder === 'asc' ? cmp : -cmp;
    }
    if (sortBy === 'Status') {
      const cmp = a.status.localeCompare(b.status);
      return sortOrder === 'asc' ? cmp : -cmp;
    }
    if (sortBy === 'Users') {
      const cmp = (a.activeUsers || 0) - (b.activeUsers || 0);
      return sortOrder === 'asc' ? cmp : -cmp;
    }
    return 0;
  });

  // Split into Pinned vs Regular
  const pinnedBots = sortedBots.filter((b) => b.isPinned);
  const otherBots = sortedBots.filter((b) => !b.isPinned);

  // Pagination for scaling to 1000s or 20,000 bots smoothly
  const totalPaginatedCount = otherBots.length;
  const totalPages = Math.max(1, Math.ceil(totalPaginatedCount / pageSize));
  const currentPageClamped = Math.min(Math.max(1, currentPage), totalPages);
  const startIndex = totalPaginatedCount > 0 ? (currentPageClamped - 1) * pageSize : 0;
  const endIndex = Math.min(startIndex + pageSize, totalPaginatedCount);
  const paginatedOtherBots = otherBots.slice(startIndex, endIndex);

  // Status style helper
  const getStatusBadge = (status: BotStatus) => {
    switch (status) {
      case 'working':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Working
          </span>
        );
      case 'stopped':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            Stopped
          </span>
        );
      case 'cloned':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300 border border-purple-300 dark:border-purple-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />
            Cloned
          </span>
        );
      case 'transferred':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border border-blue-300 dark:border-blue-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
            Transferred
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
            {status}
          </span>
        );
    }
  };

  const renderBotCard = (bot: BotItem) => {
    const isIdRevealed = !!revealedIds[bot.id];
    const isSelected = selectedBotIds.includes(bot.id);
    return (
      <motion.div
        key={bot.id}
        layout
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        whileHover={{ y: -2 }}
        onPointerDown={(e) => {
          // Don't start long-press on interactive controls
          const t = e.target as HTMLElement;
          if (t.closest('button, a, input, select, textarea, label')) return;
          onCardPointerDown(bot.id);
        }}
        onPointerUp={onCardPointerUp}
        onPointerLeave={onCardPointerUp}
        onPointerCancel={onCardPointerUp}
        onClick={(e) => {
          if (longPressTriggered.current) {
            e.preventDefault();
            e.stopPropagation();
            longPressTriggered.current = false;
            return;
          }
          if (selectionMode) {
            e.preventDefault();
            e.stopPropagation();
            handleToggleSelectBot(bot.id);
          }
        }}
        className={`glass-panel p-3.5 rounded-2xl flex flex-col justify-between gap-2.5 transition-all duration-200 shadow-xs relative group border select-none ${
          isSelected
            ? 'border-blue-500 bg-blue-50/20 dark:bg-blue-950/25 ring-1 ring-blue-500/50'
            : 'border-slate-200 dark:border-slate-800 hover:border-blue-500/60'
        }`}
      >
        {/* Top: Avatar, Checkbox (only in selection mode), Name + @username, Pin, Status */}
        <div className="flex items-start justify-between gap-2 min-w-0">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            {/* Checkmark only after long-press selection mode */}
            {selectionMode && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleToggleSelectBot(bot.id);
                }}
                className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 cursor-pointer transition ${
                  isSelected
                    ? 'bg-blue-600 border-blue-600 text-white'
                    : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-600 text-transparent'
                }`}
                aria-label={`Select ${bot.name}`}
              >
                {isSelected && <Check className="w-3.5 h-3.5 stroke-[3]" />}
              </button>
            )}

            <BotAvatar src={bot.photoUrl} alt={bot.name} className="w-9 h-9 rounded-full shadow-xs shrink-0 border border-slate-200 dark:border-slate-700" iconClassName="w-4 h-4" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1">
                <span className="text-[11px] text-blue-600 dark:text-blue-400 font-mono font-semibold break-all">
                  {bot.username}
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCopy(bot.username, 'Username');
                  }}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-0.5 cursor-pointer"
                  title="Copy bot username"
                >
                  <Copy className="w-3 h-3" />
                </button>
                <a
                  href={`https://t.me/${bot.username.replace('@', '')}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="p-0.5 text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer"
                  title="Open in Telegram"
                >
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={(e) => handleTogglePin(bot, e)}
              className="p-1 rounded-lg text-slate-400 hover:text-blue-600 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              title={bot.isPinned ? 'Unpin bot' : 'Pin bot to top'}
            >
              <Pin
                className={`w-3.5 h-3.5 ${
                  bot.isPinned ? 'text-blue-600 fill-blue-600' : ''
                }`}
              />
            </button>
          </div>
        </div>
        <h3 title={bot.name} className="font-bold text-sm text-slate-900 dark:text-white break-words line-clamp-4 leading-snug">
          {bot.name}
        </h3>
        <div className="flex">{getStatusBadge(bot.status)}</div>

        {/* Middle Stats & ID Bar */}
        <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/50 text-[11px]">
          <div className="flex items-center gap-1.5 font-mono text-slate-500 dark:text-slate-400">
            <span>ID</span>
            <span>{isIdRevealed ? bot.botNumericId : '••••' + bot.botNumericId.slice(-4)}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                toggleRevealId(bot.id);
              }}
              className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
              title={isIdRevealed ? 'Hide ID' : 'Reveal ID'}
            >
              {isIdRevealed ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
            </button>
            {isIdRevealed && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleCopy(bot.botNumericId, 'Bot ID');
                }}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                title="Copy ID"
              >
                <Copy className="w-3 h-3" />
              </button>
            )}
          </div>

          <div className="flex items-center gap-2.5 text-slate-600 dark:text-slate-300 font-semibold">
            <span>
              {bot.activeUsers}{' '}
              <span className="text-[10px] text-slate-400 font-normal">users</span>
            </span>
            <span>
              {(bot.commands?.length ?? bot.totalCommands ?? 0)}{' '}
              <span className="text-[10px] text-slate-400 font-normal font-mono">cmds</span>
            </span>
          </div>
        </div>

        {/* Bottom Actions Row: Folder tag + Edit + Start/Stop + Delete */}
        <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between gap-1.5">
          <div className="flex items-center gap-1 text-[10px] font-bold text-slate-400 truncate max-w-[100px]">
            <Folder className="w-3 h-3 text-amber-500 shrink-0" />
            <span className="truncate">{bot.folder || 'Main Bots'}</span>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {/* Edit Button -> Opens full Bot Studio */}
            <button
              type="button"
              onClick={() => onOpenEditor(bot)}
              className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-bold shadow-xs flex items-center gap-1 transition-colors cursor-pointer"
              title="Open Bot Code Editor Studio"
            >
              <Edit3 className="w-3 h-3" />
              <span>Edit</span>
            </button>

            {/* Start / Stop Button with confirmation */}
            <button
              type="button"
              onClick={(e) => handlePromptToggleStatus(bot, e)}
              className={`p-1.5 rounded-lg border transition-colors cursor-pointer ${
                bot.status === 'working'
                  ? 'border-amber-200 dark:border-amber-900/60 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/40'
                  : 'border-emerald-200 dark:border-emerald-900/60 text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/40'
              }`}
              title={bot.status === 'working' ? 'Stop Bot' : 'Start Bot'}
            >
              {bot.status === 'working' ? (
                <Square className="w-3 h-3" />
              ) : (
                <Play className="w-3 h-3" />
              )}
            </button>

            {/* Delete / Move to recycle bin button */}
            <button
              type="button"
              onClick={(e) => handlePromptDelete(bot, e)}
              className="p-1.5 rounded-lg border border-rose-200 dark:border-rose-900/60 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
              title="Delete Bot"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        </div>
      </motion.div>
    );
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Toast Alert */}
      <AnimatePresence>
        {toastMessage && (
          <motion.div
            initial={{ opacity: 0, y: -15 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -15 }}
            className="fixed top-5 right-5 z-50 px-4 py-2.5 rounded-2xl bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-2xl text-xs font-bold border border-slate-700 flex items-center gap-2"
          >
            <Check className="w-4 h-4 text-emerald-400 dark:text-emerald-600" />
            <span>{toastMessage}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Confirmation Modal for Start, Stop, Delete */}
      <AnimatePresence>
        {confirmModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-panel w-full max-w-md rounded-3xl p-6 shadow-2xl border border-slate-300 dark:border-slate-800 space-y-4"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-10 h-10 rounded-2xl flex items-center justify-center ${
                    confirmModal.isDanger
                      ? 'bg-rose-100 dark:bg-rose-950/60 text-rose-600'
                      : 'bg-blue-100 dark:bg-blue-950/60 text-blue-600'
                  }`}
                >
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  {confirmModal.title}
                </h3>
              </div>
              <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed font-medium">
                {confirmModal.message}
              </p>
              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setConfirmModal(null)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={confirmModal.onConfirm}
                  className={`px-4 py-2 rounded-xl text-xs font-bold text-white shadow-md transition-colors cursor-pointer ${
                    confirmModal.isDanger
                      ? 'bg-rose-600 hover:bg-rose-700 shadow-rose-500/20'
                      : 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/20'
                  }`}
                >
                  {confirmModal.actionLabel}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Top Header: Title, New Folder, Create Bot */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white tracking-tight">
            My Telegram Bots
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-300 mt-1 font-medium">
            Organize bots into folders, inspect code in the bot editor, and manage live clusters.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* New Folder Button as requested */}
          <button
            onClick={() => setShowNewFolderModal(true)}
            className="px-4 py-2.5 rounded-2xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:border-blue-500 text-slate-800 dark:text-slate-200 font-bold text-xs flex items-center gap-2 shadow-xs transition-colors cursor-pointer"
          >
            <FolderPlus className="w-4 h-4 text-amber-500" />
            <span>New Folder</span>
          </button>

          {/* Create New Bot Button */}
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2.5 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 flex items-center gap-2 cursor-pointer transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Create New Bot</span>
          </button>
        </div>
      </div>

      {/* Folders Bar & Controls */}
      <div className="glass-panel p-4 rounded-3xl space-y-3.5">
        {/* Row 1: Folder navigation bar with < and > arrows */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider shrink-0 flex items-center gap-1">
            <Folder className="w-3.5 h-3.5 text-amber-500" />
            Folders:
          </span>

          <div className="flex-1 flex items-center gap-1 bg-slate-100 dark:bg-slate-800/80 p-1 rounded-2xl border border-slate-200 dark:border-slate-700/60 overflow-hidden min-w-0">
            <button
              type="button"
              onClick={handlePrevFolder}
              className="p-1.5 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors cursor-pointer shrink-0"
              title="Previous folder"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>

            <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none py-0.5 px-1 min-w-0 flex-1">
              <button
                type="button"
                onClick={() => handleSelectFolder('All')}
                className={`px-3 py-1 rounded-xl text-xs font-bold whitespace-nowrap transition-colors cursor-pointer shrink-0 ${
                  selectedFolder === 'All'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
                }`}
              >
                All Folders ({activeBots.length})
              </button>
              {folders.map((f) => {
                const countInFolder = activeBots.filter((b) => (b.folder || 'Main Bots') === f).length;
                return (
                  <button
                    key={f}
                    type="button"
                    onClick={() => handleSelectFolder(f)}
                    className={`px-3 py-1 rounded-xl text-xs font-bold whitespace-nowrap transition-colors cursor-pointer flex items-center gap-1.5 shrink-0 ${
                      selectedFolder === f
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
                    }`}
                  >
                    <span>{f}</span>
                    <span className="text-[10px] opacity-75">({countInFolder})</span>
                  </button>
                );
              })}
            </div>

            <button
              type="button"
              onClick={handleNextFolder}
              className="p-1.5 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors cursor-pointer shrink-0"
              title="Next folder"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Row 2: Search, Status Carousel with < and >, and Sort */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 pt-2 border-t border-slate-200 dark:border-slate-800">
          {/* Search input */}
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={localSearch}
              onChange={(e) => setLocalSearch(e.target.value)}
              placeholder="Search by bot name, username, or numeric ID..."
              className="w-full pl-10 pr-4 py-2 rounded-2xl text-xs bg-slate-100 dark:bg-slate-800/90 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 font-medium"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* 4 Status Filters with < and > arrows (All, working, stopped, cloned, transferred) */}
            <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/80 p-1 rounded-2xl border border-slate-200 dark:border-slate-700/60 overflow-hidden max-w-full">
              <button
                type="button"
                onClick={handlePrevStatus}
                className="p-1.5 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors cursor-pointer shrink-0"
                title="Previous status"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <div className="flex items-center gap-1 overflow-x-auto scrollbar-none py-0.5 px-1 min-w-0 max-w-[260px] sm:max-w-[340px]">
                {statusList.map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => handleSelectStatus(st)}
                    className={`px-2.5 py-1 rounded-xl text-xs font-bold capitalize whitespace-nowrap transition-colors cursor-pointer shrink-0 ${
                      filterStatus.toLowerCase() === st.toLowerCase()
                        ? 'bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-300 shadow-xs'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={handleNextStatus}
                className="p-1.5 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors cursor-pointer shrink-0"
                title="Next status"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Sort by: Name, Status, Users */}
            <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/70 p-1 rounded-2xl border border-slate-200 dark:border-slate-700/60">
              <span className="text-[11px] font-bold text-slate-500 px-1.5 flex items-center gap-1">
                <ArrowUpDown className="w-3 h-3" />
                Sort:
              </span>
              {(['Name', 'Status', 'Users'] as const).map((crit) => (
                <button
                  key={crit}
                  type="button"
                  onClick={() => {
                    if (sortBy === crit) {
                      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
                    } else {
                      setSortBy(crit);
                      setSortOrder('asc');
                    }
                  }}
                  className={`px-2 py-1 rounded-xl text-xs font-bold transition-colors cursor-pointer ${
                    sortBy === crit
                      ? 'bg-blue-600 text-white shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  {crit} {sortBy === crit ? (sortOrder === 'asc' ? '↑' : '↓') : ''}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Bulk Operations Action Bar (visible only in selection mode) */}
      {selectionMode && selectedBotIds.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-3.5 rounded-2xl bg-blue-500/10 border border-blue-500/30 flex flex-wrap items-center justify-between gap-3 text-xs"
        >
          <div className="flex items-center gap-2.5">
            <span className="font-bold text-blue-600 dark:text-blue-400">
              {selectedBotIds.length} bot{selectedBotIds.length > 1 ? 's' : ''} selected
            </span>
            <span className="text-slate-400">•</span>
            <button
              type="button"
              onClick={clearSelection}
              className="text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 underline text-[11px] cursor-pointer"
            >
              Clear selection
            </button>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1.5">
              <Folder className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 shrink-0" />
              <select
                defaultValue=""
                onChange={(e) => {
                  const v = e.target.value;
                  if (v) handleBulkMoveToFolder(v);
                  e.target.value = '';
                }}
                className="px-2 py-1.5 rounded-xl text-xs font-bold bg-white dark:bg-slate-900 border border-blue-300 dark:border-blue-800 text-slate-800 dark:text-slate-100 cursor-pointer max-w-[140px]"
                title="Move selected bots into a folder"
              >
                <option value="" disabled>
                  Move to folder…
                </option>
                {folders.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
                <option value="Main Bots">Main Bots</option>
              </select>
            </div>
            <button
              type="button"
              onClick={handleBulkStart}
              className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Start</span>
            </button>
            <button
              type="button"
              onClick={handleBulkStop}
              className="px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
            >
              <Square className="w-3.5 h-3.5" />
              <span>Stop</span>
            </button>
            <button
              type="button"
              onClick={handleBulkDelete}
              className="px-3 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Move to Bin</span>
            </button>
          </div>
        </motion.div>
      )}

      {/* Bot Cards Grid or Skeleton during Transition */}
      {isTransitioning ? (
        <MyBotsCardsSkeleton count={8} />
      ) : (
        <>
          {/* Pinned Section: Pinned ↓ */}
          {pinnedBots.length > 0 && (
            <div className="space-y-2.5">
              <div className="flex items-center gap-2">
                <Pin className="w-4 h-4 text-blue-600 fill-blue-600" />
                <h2 className="text-sm font-black text-slate-900 dark:text-white uppercase tracking-wider">
                  Pinned ↓
                </h2>
                <span className="text-xs font-bold text-slate-400">({pinnedBots.length})</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {pinnedBots.map(renderBotCard)}
              </div>
            </div>
          )}

          {/* Main / Other Bots Section */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              {pinnedBots.length > 0 && otherBots.length > 0 ? (
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                  All Bots ({totalPaginatedCount})
                </h2>
              ) : (
                <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                  Bots Directory ({totalPaginatedCount})
                </span>
              )}

              {/* Select All only after selection mode is active (long-press first) */}
              {selectionMode && paginatedOtherBots.length > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    const pageIds = paginatedOtherBots.map((b) => b.id);
                    const allPageSelected = pageIds.every((id) => selectedBotIds.includes(id));
                    if (allPageSelected) {
                      setSelectedBotIds((prev) => {
                        const next = prev.filter((id) => !pageIds.includes(id));
                        if (next.length === 0) setSelectionMode(false);
                        return next;
                      });
                    } else {
                      setSelectionMode(true);
                      setSelectedBotIds((prev) => Array.from(new Set([...prev, ...pageIds])));
                    }
                  }}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1 cursor-pointer font-semibold"
                >
                  <CheckSquare className="w-3.5 h-3.5" />
                  <span>
                    {paginatedOtherBots.every((b) => selectedBotIds.includes(b.id))
                      ? 'Deselect Page'
                      : 'Select All on Page'}
                  </span>
                </button>
              )}
              {!selectionMode && paginatedOtherBots.length > 0 && (
                <span className="text-[10px] text-slate-400 font-medium hidden sm:inline">
                  Hold a bot card to multi-select
                </span>
              )}
            </div>

            {otherBots.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {paginatedOtherBots.map(renderBotCard)}
              </div>
            ) : pinnedBots.length === 0 ? (
              <div className="glass-panel p-12 text-center rounded-3xl space-y-3">
                <Bot className="w-12 h-12 text-slate-400 mx-auto" />
                <h3 className="text-base font-bold text-slate-900 dark:text-white">
                  No bots found
                </h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  No bots match your selected folder "{selectedFolder}", status filter "{filterStatus}", or search query.
                </p>
              </div>
            ) : null}

            {/* Pagination Controls Bar for Scaling up to 20,000 bots */}
            {otherBots.length > 0 && (
              <div className="glass-panel p-3.5 sm:p-4 rounded-2xl border border-slate-200/80 dark:border-slate-800/80 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs mt-4">
                <div className="flex flex-wrap items-center gap-2 text-slate-500">
                  <span>
                    Showing <strong className="text-slate-900 dark:text-white font-bold">{startIndex + 1}</strong>–<strong className="text-slate-900 dark:text-white font-bold">{endIndex}</strong> of <strong className="text-slate-900 dark:text-white font-bold">{totalPaginatedCount.toLocaleString()}</strong> bots
                  </span>
                  <span className="text-slate-300 dark:text-slate-700">|</span>
                  <div className="flex items-center gap-1.5">
                    <span>Rows</span>
                    <select
                      value={pageSize}
                      onChange={(e) => {
                        setPageSize(Number(e.target.value));
                        setCurrentPage(1);
                        triggerTransition();
                      }}
                      className="px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-bold focus:outline-none cursor-pointer text-xs"
                    >
                      <option value={10}>10</option>
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                      <option value={500}>500</option>
                      <option value={1000}>1000</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    disabled={currentPageClamped <= 1}
                    onClick={() => {
                      setCurrentPage((p) => Math.max(1, p - 1));
                      triggerTransition();
                    }}
                    className="p-1.5 rounded-xl border border-slate-200 dark:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                    title="Previous Page"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>

                  {/* Page number buttons */}
                  <div className="flex items-center gap-1">
                    {Array.from({ length: Math.min(5, totalPages) }).map((_, idx) => {
                      let pageNum = idx + 1;
                      if (totalPages > 5 && currentPageClamped > 3) {
                        pageNum = currentPageClamped - 2 + idx;
                        if (pageNum > totalPages) pageNum = totalPages - (4 - idx);
                      }
                      return (
                        <button
                          key={pageNum}
                          type="button"
                          onClick={() => {
                            setCurrentPage(pageNum);
                            triggerTransition();
                          }}
                          className={`w-8 h-8 rounded-xl font-bold transition-all cursor-pointer text-xs ${
                            currentPageClamped === pageNum
                              ? 'bg-blue-600 text-white shadow-xs'
                              : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                          }`}
                        >
                          {pageNum}
                        </button>
                      );
                    })}
                    {totalPages > 5 && currentPageClamped < totalPages - 2 && (
                      <span className="px-1 text-slate-400">...</span>
                    )}
                  </div>

                  <button
                    type="button"
                    disabled={currentPageClamped >= totalPages}
                    onClick={() => {
                      setCurrentPage((p) => Math.min(totalPages, p + 1));
                      triggerTransition();
                    }}
                    className="p-1.5 rounded-xl border border-slate-200 dark:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                    title="Next Page"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* New Folder Modal */}
      <AnimatePresence>
        {showNewFolderModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-panel w-full max-w-sm rounded-3xl p-6 shadow-2xl border border-slate-300 dark:border-slate-800 space-y-4"
            >
              <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <FolderPlus className="w-5 h-5 text-amber-500" />
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    New Folder
                  </h3>
                </div>
                <button
                  onClick={() => setShowNewFolderModal(false)}
                  className="text-slate-400 hover:text-slate-700"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleCreateFolder} className="space-y-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1">
                    Folder Name
                  </label>
                  <input
                    type="text"
                    required
                    value={newFolderNameInput}
                    onChange={(e) => setNewFolderNameInput(e.target.value)}
                    placeholder="e.g. VIP Bots, Crypto, Automation"
                    className="w-full px-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowNewFolderModal(false)}
                    className="px-3.5 py-2 rounded-xl text-xs font-bold text-slate-600"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs"
                  >
                    Create Folder
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Create New Bot Modal */}
      <AnimatePresence>
        {showCreateModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-panel w-full max-w-md rounded-3xl p-6 shadow-2xl border border-slate-300 dark:border-slate-800 space-y-4"
            >
              <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-blue-600" />
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    Connect New Telegram Bot
                  </h3>
                </div>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="text-slate-400 hover:text-slate-700"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleCreateSubmit} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-1">
                    Bot API Token (From @BotFather)
                  </label>
                  <input
                    type="text"
                    required
                    value={newBotToken}
                    onChange={(e) => { setNewBotToken(e.target.value); if (createError) setCreateError(''); }}
                    placeholder="e.g. 729104829:AAHq_mXZe9..."
                    autoComplete="off"
                    spellCheck={false}
                    className={`w-full px-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border text-slate-900 dark:text-white font-mono ${createError ? 'border-rose-500' : 'border-slate-300 dark:border-slate-700'}`}
                  />
                  {createError && (
                    <div role="alert" className="mt-2 flex items-start gap-2 px-3 py-2 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-[11px] font-semibold text-rose-700 dark:text-rose-300">
                      <span className="shrink-0">⚠️</span>
                      <span>{createError}</span>
                    </div>
                  )}
                </div>

                {folders.length > 0 && (
                <div>
                  <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-1">
                    Folder
                  </label>
                  <select
                    value={newBotFolder}
                    onChange={(e) => setNewBotFolder(e.target.value)}
                    className="w-full px-3.5 py-2 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white"
                  >
                    <option value="">No folder</option>
                    {folders.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </div>
                )}

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => { setShowCreateModal(false); setCreateError(''); }}
                    className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-200/60 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isCreating}
                    className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-bold text-xs shadow-md shadow-blue-500/20 cursor-pointer"
                  >
                    {isCreating ? 'Connecting…' : 'Connect Bot'}
                  </button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
