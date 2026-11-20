import React, { useState, useRef, useEffect, useMemo } from 'react';
import { BotAvatar } from './BotAvatar';
import { motion, AnimatePresence } from 'motion/react';
import {
  Radio,
  Plus,
  ArrowLeft,
  Search,
  Check,
  X,
  Send,
  Sparkles,
  Layers,
  ExternalLink,
  Bot,
  Trash2,
  Clock,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Activity,
  Eye,
  Link,
  Users,
  Play,
  Pause,
  Copy,
  Terminal,
  Globe,
  Share2,
  Code,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Lock,
  Sliders,
  XCircle,
  Filter,
  ShieldAlert,
  Hash,
  Hourglass,
  Link2,
  Upload,
  Pin,
  Languages,
} from 'lucide-react';
import { BotItem, BroadcastItem, InlineButton, TelegramButtonType, BotBroadcastStats } from '../types';
import { BroadcastCardsSkeleton } from './SkeletonScreen';
import { apiService } from '../services/apiService';

export function formatDuration(seconds: number): string {
  if (seconds < 0) seconds = 0;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m === 0) {
    return `${s}s`;
  }
  return `${m}m ${s}s`;
}

interface ActionConfirmModalState {
  isOpen: boolean;
  type: 'cancel_campaign' | 'pause_campaign' | 'resume_campaign' | 'cancel_bot' | 'pause_bot' | 'resume_bot';
  broadcast: BroadcastItem;
  botId?: string;
  botName?: string;
  botUsername?: string;
}

interface BroadcastViewProps {
  bots: BotItem[];
  broadcasts: BroadcastItem[];
  onSendBroadcast: (broadcast: BroadcastItem) => void;
  onDeleteBroadcast?: (id: string) => void;
  onUpdateBroadcast?: (broadcast: BroadcastItem) => void;
  onRefreshBroadcasts?: () => void;
  onOpenBot?: (botId: string, broadcastTitle: string) => void;
}

const NO_CAPTION_TYPES = ['Sticker', 'VidNote'];
// Telegram message kinds that carry no file: their fields are typed in directly (Bot Broadcast docs: send_location, send_venue, send_contact, send_poll, send_dice, forward_message)
const DATA_TYPES: string[] = ['Location', 'Venue', 'Contact', 'Poll', 'Dice', 'Forward'];
const DATA_FIELDS: Record<string, { key: string; label: string; ph: string; req?: boolean }[]> = {
  Location: [{ key: 'latitude', label: 'Latitude', ph: '23.8103', req: true }, { key: 'longitude', label: 'Longitude', ph: '90.4125', req: true }],
  Venue: [{ key: 'title', label: 'Title', ph: 'Office', req: true }, { key: 'address', label: 'Address', ph: 'Road 1, Dhaka', req: true }, { key: 'latitude', label: 'Latitude', ph: '23.8103', req: true }, { key: 'longitude', label: 'Longitude', ph: '90.4125', req: true }],
  Contact: [{ key: 'phone_number', label: 'Phone number', ph: '+8801700000000', req: true }, { key: 'first_name', label: 'First name', ph: 'Support', req: true }, { key: 'last_name', label: 'Last name (optional)', ph: '' }],
  Poll: [{ key: 'question', label: 'Question', ph: 'Do you like our bot?', req: true }],
  Dice: [],
  Forward: [{ key: 'from_chat_id', label: 'From chat (id or @channel)', ph: '@mychannel', req: true }, { key: 'message_id', label: 'Message ID', ph: '123', req: true }],
};
const DICE_EMOJI = ['🎲', '🎯', '🏀', '⚽', '🎳', '🎰'];
const buildDataText = (type: string, f: Record<string, string>): string => {
  const o: Record<string, any> = {};
  (DATA_FIELDS[type] || []).forEach(({ key }) => { const v = (f[key] || '').trim(); if (v) o[key] = v; });
  if (type === 'Poll') { o.options = (f.options || '').split('\n').map((x) => x.trim()).filter(Boolean); o.is_anonymous = f.anonymous !== 'no'; o.allows_multiple_answers = f.multiple === 'yes'; }
  if (type === 'Dice') o.emoji = f.emoji || '🎲';
  return JSON.stringify(o);
};
const PERSONALIZE_TAGS: [string, string][] = [
  ['{first_name}', 'First name, e.g. Alex'],
  ['{user_name}', 'Full name as shown on Telegram'],
  ['{username}', '@username (falls back to the name if the user has none)'],
  ['{user_id}', 'Telegram user ID'],
  ['{mention}', 'Clickable name that opens the user (HTML / Markdown modes)'],
];

export const BroadcastView: React.FC<BroadcastViewProps> = ({
  bots,
  broadcasts,
  onSendBroadcast,
  onDeleteBroadcast,
  onUpdateBroadcast,
  onRefreshBroadcasts,
  onOpenBot,
}) => {
  const focusBotId = (() => { try { return localStorage.getItem('bm_broadcast_focus_bot') || ''; } catch { return ''; } })();
  const [activeTab, setActiveTab] = useState<'All' | 'Active' | 'Done' | 'Failed'>(() => {
    try { const v = localStorage.getItem('bm_broadcast_tab'); if (v === 'All' || v === 'Active' || v === 'Done' || v === 'Failed') return v; } catch {}
    return 'All';
  });
  useEffect(() => { try { localStorage.setItem('bm_broadcast_tab', activeTab); } catch {} }, [activeTab]);
  const [isCreatingNew, setIsCreatingNew] = useState(false);

  // Live Details Modal & Clean System State
  const [selectedBroadcastForDetails, setSelectedBroadcastForDetails] = useState<BroadcastItem | null>(null);
  // keep the details page live: follow the polled broadcasts list
  useEffect(() => {
    setSelectedBroadcastForDetails((cur) => {
      if (!cur) return cur;
      const fresh = broadcasts.find((b) => b.id === cur.id);
      return fresh ? fresh : cur;
    });
  }, [broadcasts]);
  const hadDetailsRef = useRef(false);
  useEffect(() => {
    try {
      if (selectedBroadcastForDetails) { localStorage.setItem('bm_broadcast_open', selectedBroadcastForDetails.id); hadDetailsRef.current = true; }
      else if (hadDetailsRef.current) { hadDetailsRef.current = false; localStorage.removeItem('bm_broadcast_open'); localStorage.removeItem('bm_broadcast_focus_bot'); }
    } catch {}
  }, [selectedBroadcastForDetails?.id]);
  useEffect(() => {
    if (selectedBroadcastForDetails || !broadcasts.length) return;
    try {
      const id = localStorage.getItem('bm_broadcast_open');
      const f = id && broadcasts.find((b) => b.id === id);
      if (f) setSelectedBroadcastForDetails(f);
    } catch {}
  }, [broadcasts.length]);
  const [confirmCleanModal, setConfirmCleanModal] = useState<{
    isOpen: boolean;
    broadcast: BroadcastItem;
  } | null>(null);
  const [actionConfirmModal, setActionConfirmModal] = useState<ActionConfirmModalState | null>(null);
  const [actionToast, setActionToast] = useState<string | null>(null);

  const showActionToast = (msg: string) => {
    setActionToast(msg);
    setTimeout(() => setActionToast(null), 3000);
  };

  const syncFromServer = async (id: string) => {
    try {
      const fresh = await apiService.getBroadcast(id);
      if (onUpdateBroadcast) onUpdateBroadcast(fresh);
      setSelectedBroadcastForDetails((cur) => (cur && cur.id === id ? fresh : cur));
    } catch {
      onRefreshBroadcasts?.();
    }
  };

  const handleConfirmClean = async (targetBc: BroadcastItem) => {
    try {
      const res: any = await apiService.cleanFailedBroadcast(targetBc.id);
      await syncFromServer(targetBc.id);
      const n = res?.cleaned ?? 0;
      showActionToast(n ? `Cleaned ${n.toLocaleString()} unreachable user${n !== 1 ? 's' : ''} — they return automatically if they start the bot again` : 'Nobody to clean — those users already started the bot again or were cleaned before');
    } catch (e: any) {
      showActionToast(e?.message || 'Could not clean failed users');
    }
    setConfirmCleanModal(null);
  };

  // New broadcast form state
  const [selectedBotIds, setSelectedBotIds] = useState<string[]>([]);
  const [showSelectBotsModal, setShowSelectBotsModal] = useState(false);
  // showSelectBotsModal body lock — keep underlying broadcast page from scrolling
  useEffect(() => {
    if (!showSelectBotsModal) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [showSelectBotsModal]);
  const [botSearchQuery, setBotSearchQuery] = useState('');

  const [messageType, setMessageType] = useState<
    'Text' | 'Photo' | 'Video' | 'Audio' | 'Doc' | 'GIF' | 'Voice' | 'VidNote' | 'Sticker' | 'Location' | 'Venue' | 'Contact' | 'Poll' | 'Dice' | 'Forward'
  >('Text');
  const [dataFields, setDataFields] = useState<Record<string, string>>({});
  const isDataType = DATA_TYPES.includes(messageType);
  const setField = (k: string, v: string) => setDataFields((d) => ({ ...d, [k]: v }));
  const [messageText, setMessageText] = useState('');
  // Media source: pick a file from the device, or paste a link that is detected automatically
  const [mediaMode, setMediaMode] = useState<'file' | 'url'>('file');
  const [mediaId, setMediaId] = useState('');
  const [mediaName, setMediaName] = useState('');
  const [mediaUrlInput, setMediaUrlInput] = useState('');
  const [mediaBusy, setMediaBusy] = useState(false);
  const [mediaError, setMediaError] = useState('');
  const [detectedNote, setDetectedNote] = useState('');
  const lastDetected = useRef('');
  const ACCEPT_BY_TYPE: Record<string, string> = {
    Photo: 'image/*', Video: 'video/*', Audio: 'audio/*', Doc: '*/*', GIF: 'image/gif,video/mp4,video/*',
    Voice: 'audio/ogg,audio/*', VidNote: 'video/*', Sticker: 'image/webp,video/webm',
  };
  const handlePickMedia = async (file?: File | null) => {
    if (!file) return;
    setMediaError(''); setMediaBusy(true);
    try {
      const r = await apiService.uploadBroadcastMedia(file, messageType);
      setMediaId(r.mediaId); setMediaName(file.name);
    } catch (e: any) {
      setMediaId(''); setMediaName('');
      setMediaError(e?.response?.data?.error || e?.message || 'Upload failed');
    } finally { setMediaBusy(false); }
  };
  const handleDetectUrl = async (value: string) => {
    const v = value.trim();
    setMediaError(''); setDetectedNote('');
    if (!v) return;
    setMediaBusy(true);
    try {
      const d = await apiService.detectBroadcastUrl(v);
      // every new link replaces everything detected from the previous one
      setMessageType(d.type as any);
      setMessageText(NO_CAPTION_TYPES.includes(d.type) ? '' : (d.caption || '').slice(0, d.type === 'Text' ? 4096 : 1024));
      setParseMode((d.parseMode as any) || 'None');
      setInlineButtons((d.buttons || []).map((b: any, i: number) => ({ ...b, id: `det-${Date.now()}-${i}` })));
      lastDetected.current = v;
      if (d.type === 'Text') { setMediaMode('file'); setMediaUrlInput(''); }
      const nb = (d.buttons || []).length, ne = (d.customEmojiIds || []).length;
      setDetectedNote(`Detected: ${d.type === 'Text' ? 'text post' : d.type}${d.caption && d.type !== 'Text' ? ' + caption' : ''}${nb ? ` + ${nb} button${nb > 1 ? 's' : ''}` : ''}${ne ? ` + ${ne} premium emoji` : ''}${d.note ? ' — ' + d.note : ''}`);
    } catch (e: any) {
      setMediaError(e?.response?.data?.error || e?.message || 'Could not read that link');
    } finally { setMediaBusy(false); }
  };
  const [parseMode, setParseMode] = useState<'None' | 'HTML' | 'Markdown' | 'MarkdownV2'>('HTML');
  const [inlineButtons, setInlineButtons] = useState<InlineButton[]>([]);
  const [languageFilter, setLanguageFilter] = useState('');
  const [pinMessage, setPinMessage] = useState(false);
  const [newSpeed, setNewSpeed] = useState('');
  const [planLim, setPlanLim] = useState<any>({ broadcastSpeed: 30 });
  const [planName, setPlanName] = useState('');
  const [langs, setLangs] = useState<{ code: string; count: number }[]>([]);
  const [showLangs, setShowLangs] = useState(false);
  useEffect(() => {
    apiService.getPlans().then((r: any) => {
      const p = (r.plans || []).find((x: any) => x.name === r.current);
      if (p) { setPlanLim(p.limits || {}); setPlanName(p.name); }
    }).catch(() => {});
  }, []);
  useEffect(() => {
    if (!isCreatingNew || selectedBotIds.length === 0) { setLangs([]); return; }
    apiService.getBroadcastLanguages(selectedBotIds).then(setLangs).catch(() => setLangs([]));
  }, [isCreatingNew, selectedBotIds]);
  const planCap: number = Number(planLim.broadcastSpeed ?? 30) || 30;
  const SPEEDS = [5, 10, 15, 20, 30, 50, 100, 200];
  const speedOptions = [...SPEEDS.filter((s) => s <= planCap).map((s) => `${s} msgs/sec`), ...(planCap > 30 ? ['Unlimited'] : [])];
  const lockedSpeeds = [...SPEEDS.filter((s) => s > planCap).map((s) => `${s} msgs/sec`), ...(planCap <= 30 ? ['Unlimited'] : [])];
  const [targetUserLimitInput, setTargetUserLimitInput] = useState<string>('1');
  const [detailsBotSearch, setDetailsBotSearch] = useState<string>('');
  const [detailsBotStatusFilter, setDetailsBotStatusFilter] = useState<'All' | 'Delivering' | 'Paused' | 'Cancelled' | 'Done'>('All');
  const [detailsElapsedSeconds, setDetailsElapsedSeconds] = useState<number>(0);

  useEffect(() => {
    if (!selectedBroadcastForDetails) {
      setDetailsElapsedSeconds(0);
      return;
    }
    let initialSec = Math.max(0, Math.floor(selectedBroadcastForDetails.elapsedSeconds || 0));
    setDetailsElapsedSeconds(initialSec);

    if (selectedBroadcastForDetails.status === 'Active') {
      const timer = setInterval(() => {
        setDetailsElapsedSeconds((prev) => prev + 1);
      }, 1000);
      return () => clearInterval(timer);
    }
  }, [selectedBroadcastForDetails?.id, selectedBroadcastForDetails?.status]);

  const [isSending, setIsSending] = useState(false);
  const [sendSuccessToast, setSendSuccessToast] = useState(false);
  const [confirmDeleteBroadcast, setConfirmDeleteBroadcast] = useState<BroadcastItem | null>(null);

  // Minimum Broadcast Users Limit (Admin / Database Configured)
  const [minBroadcastUsers, setMinBroadcastUsers] = useState<number>(20);
  const [isEditingMinUsers, setIsEditingMinUsers] = useState(false);
  const [tempMinUsers, setTempMinUsers] = useState<string>('20');

  // Bot Modal Multi-Bot Filter & Pagination (Supports 1000 - 2000 bots cleanly)
  const [botModalFilter, setBotModalFilter] = useState<'All' | 'Eligible' | 'Selected' | 'UnderLimit'>('All');
  const [botModalPage, setBotModalPage] = useState<number>(1);
  const [botModalPageSize, setBotModalPageSize] = useState<number>(25);

  useEffect(() => {
    apiService.getBroadcastMinUsers()
      .then((res) => {
        if (res && typeof res.minBroadcastUsers === 'number') {
          setMinBroadcastUsers(res.minBroadcastUsers);
          setTempMinUsers(String(res.minBroadcastUsers));
        }
      })
      .catch(() => {});
  }, []);

  const handleSaveMinUsers = async (newVal: number) => {
    const val = Math.max(1, newVal);
    setMinBroadcastUsers(val);
    setTempMinUsers(String(val));
    setIsEditingMinUsers(false);
    try {
      await apiService.updateBroadcastMinUsers(val);
      showActionToast(`Admin limit updated: Min ${val} users required to broadcast`);
    } catch {
      showActionToast('Failed to update minimum broadcast limit');
    }
  };

  const getBotUsers = (bot: BotItem): number => {
    if (typeof bot.activeUsers === 'number') return bot.activeUsers;
    if (typeof (bot as any).totalUsers === 'number') return (bot as any).totalUsers;
    return 0;
  };

  const runAction = async (bc: BroadcastItem, fn: () => Promise<any>, okMsg: string) => {
    try {
      await fn();
      await syncFromServer(bc.id);
      showActionToast(okMsg);
    } catch (e: any) {
      await syncFromServer(bc.id);
      showActionToast(e?.message || 'Action failed');
    }
  };

  const handleTogglePauseResume = (bc: BroadcastItem, forcedStatus?: 'Active' | 'Paused') => {
    const nextStatus = forcedStatus || (bc.status === 'Active' ? 'Paused' : 'Active');
    if (['Cancelled', 'Done', 'Completed', 'Failed'].includes(bc.status)) {
      showActionToast(`${bc.status} campaigns are final and cannot be changed`);
      return;
    }
    if (nextStatus === 'Paused') {
      runAction(bc, () => apiService.pauseBroadcast(bc.id), 'Broadcast paused');
    } else {
      runAction(bc, () => apiService.resumeBroadcast(bc.id), 'Broadcast resumed');
    }
  };

  const handleCancelCampaign = (bc: BroadcastItem) => {
    runAction(bc, () => apiService.cancelBroadcast(bc.id), 'Broadcast campaign cancelled successfully');
  };

  const handleUpdateBotBroadcastStatus = (
    bc: BroadcastItem,
    botId: string,
    newStatus: 'Delivering' | 'Paused'
  ) => {
    runAction(bc, () => apiService.updateBroadcastBotStatus(bc.id, botId, newStatus), `Bot status updated to ${newStatus}`);
  };

  const handleExecuteConfirmedAction = () => {
    if (!actionConfirmModal) return;
    const { type, broadcast: bc, botId } = actionConfirmModal;

    if (type === 'cancel_campaign') {
      handleCancelCampaign(bc);
    } else if (type === 'pause_campaign') {
      handleTogglePauseResume(bc, 'Paused');
    } else if (type === 'resume_campaign') {
      handleTogglePauseResume(bc, 'Active');
    } else if (type === 'pause_bot' && botId) {
      handleUpdateBotBroadcastStatus(bc, botId, 'Paused');
    } else if (type === 'resume_bot' && botId) {
      handleUpdateBotBroadcastStatus(bc, botId, 'Delivering');
    }

    setActionConfirmModal(null);
  };

  const handleUpdateDeliverySpeed = (bc: BroadcastItem, newSpeed: string) => {
    runAction(bc, () => apiService.updateBroadcastSpeed(bc.id, newSpeed), `Broadcast delivery speed set to ${newSpeed}`);
  };

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Pagination for broadcasts
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(6);
  const [isTransitioning, setIsTransitioning] = useState(false);

  const handlePageChange = (page: number) => {
    setIsTransitioning(true);
    setCurrentPage(page);
    setTimeout(() => {
      setIsTransitioning(false);
    }, 200);
  };

  const handlePageSizeChange = (size: number) => {
    setIsTransitioning(true);
    setPageSize(size);
    setCurrentPage(1);
    setTimeout(() => {
      setIsTransitioning(false);
    }, 200);
  };

  // Filtered broadcast list
  const filteredBroadcasts = broadcasts.filter((b) => {
    if (activeTab === 'All') return true;
    return b.status === activeTab;
  });

  const totalPages = Math.max(1, Math.ceil(filteredBroadcasts.length / pageSize));
  const safePage = Math.min(Math.max(1, currentPage), totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const paginatedBroadcasts = filteredBroadcasts.slice(startIndex, startIndex + pageSize);

  // Insert personalization tag at cursor
  const handleInsertTag = (tag: string) => {
    if (!textareaRef.current) {
      setMessageText((prev) => prev + tag);
      return;
    }
    const textarea = textareaRef.current;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const newText = messageText.substring(0, start) + tag + messageText.substring(end);
    setMessageText(newText);
    setTimeout(() => {
      textarea.focus();
      textarea.setSelectionRange(start + tag.length, start + tag.length);
    }, 50);
  };

  // Bot selection toggles with minimum user qualification check
  const handleToggleBot = (bot: BotItem) => {
    const userCount = getBotUsers(bot);
    if (userCount < minBroadcastUsers) {
      showActionToast(`Cannot select ${bot.name}: Has only ${userCount} users. Minimum ${minBroadcastUsers} users required.`);
      return;
    }
    if (selectedBotIds.includes(bot.id)) {
      setSelectedBotIds(selectedBotIds.filter((id) => id !== bot.id));
    } else {
      setSelectedBotIds([...selectedBotIds, bot.id]);
    }
  };

  const handleSelectAllEligibleBots = () => {
    const eligibleBots = bots.filter((b) => getBotUsers(b) >= minBroadcastUsers);
    setSelectedBotIds(eligibleBots.map((b) => b.id));
    showActionToast(`Selected ${eligibleBots.length} eligible bot${eligibleBots.length !== 1 ? 's' : ''} (min ${minBroadcastUsers} users)`);
  };

  const handleClearSelectedBots = () => {
    setSelectedBotIds([]);
  };

  // Inline buttons manager with all Telegram button types
  const handleAddButton = (type: TelegramButtonType = 'url') => {
    const defaultText =
      type === 'url'
        ? 'Open Link'
        : type === 'callback_data'
        ? 'Confirm Action'
        : type === 'web_app'
        ? 'Launch Mini App'
        : type === 'switch_inline_query'
        ? 'Share with Friends'
        : 'Copy Code';

    setInlineButtons([
      ...inlineButtons,
      {
        id: `btn-${Date.now()}-${Math.random().toString(16).substring(2, 6)}`,
        row: Math.max(0, ...inlineButtons.map((b) => b.row || 0)) + 1,
        text: defaultText,
        type,
        url: type === 'url' ? 'https://t.me/' : '',
        callbackData: type === 'callback_data' ? 'action_payload' : '',
        webAppUrl: type === 'web_app' ? 'https://' : '',
        switchInlineQuery: type === 'switch_inline_query' ? 'query' : '',
        copyText: type === 'copy_text' ? 'TELEBOT-2026' : '',
      },
    ]);
  };

  const handleRemoveButton = (btnId: string) => {
    setInlineButtons(inlineButtons.filter((b) => b.id !== btnId));
  };

  const handleUpdateButton = (btnId: string, patch: Partial<InlineButton>) => {
    setInlineButtons(
      inlineButtons.map((b) => (b.id === btnId ? { ...b, ...patch } : b))
    );
  };

  // Send Broadcast Action
  const handleDispatchBroadcast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSending) return;
    if (isDataType) {
      const miss = (DATA_FIELDS[messageType] || []).find((x) => x.req && !(dataFields[x.key] || '').trim());
      if (miss) { setMediaError(`${messageType}: ${miss.label} is required.`); return; }
      if (messageType === 'Poll' && (dataFields.options || '').split('\n').map((x) => x.trim()).filter(Boolean).length < 2) { setMediaError('A poll needs at least 2 options (one per line).'); return; }
    }
    const hasMedia = messageType !== 'Text' && (mediaMode === 'url' ? !!mediaUrlInput.trim() : !!mediaId);
    if (!isDataType && !messageText.trim() && !hasMedia) {
      setMediaError(messageType === 'Text' ? 'Write a message first.' : 'Add the media first.');
      return;
    }
    if (!isDataType && messageType !== 'Text' && !hasMedia) {
      setMediaError(mediaMode === 'url' ? 'Paste a media link first.' : `Choose the ${messageType.toLowerCase()} first.`);
      return;
    }
    if (selectedBotIds.length === 0) {
      alert('Select at least one bot');
      return;
    }
    // Block if any Active/Paused campaign exists in list
    const running = broadcasts.find((b) => b.status === 'Active' || b.status === 'Paused');
    if (running) {
      alert('A broadcast is already running. Wait until it completes or cancel it first.');
      return;
    }
    setIsSending(true);
    try {
      const payload = {
        title: isDataType ? `${messageType} broadcast` : messageText.slice(0, 32) + (messageText.length > 32 ? '...' : ''),
        targetBotIds: selectedBotIds,
        targetBotUsernames: bots.filter((b) => selectedBotIds.includes(b.id)).map((b) => b.username),
        messageType,
        messageText: isDataType ? buildDataText(messageType, dataFields) : messageText,
        mediaSource: messageType === 'Text' || isDataType ? '' : mediaMode === 'url' ? 'url' : 'upload',
        mediaRef: messageType === 'Text' || isDataType ? '' : mediaMode === 'url' ? mediaUrlInput.trim() : mediaId,
        parseMode,
        inlineButtons,
        languageFilter: languageFilter.trim() || 'All',
        pinMessage,
        deliverySpeed: newSpeed || (planCap > 30 ? 'Unlimited' : `${planCap} msgs/sec`),
        targetUserLimit: (() => {
          const raw = (targetUserLimitInput || '').trim();
          if (!raw || raw.toLowerCase() === 'all') return 1; // default limit 1
          const n = Number(String(raw).replace(/,/g, ''));
          return Number.isFinite(n) && n > 0 ? n : 1;
        })(),
      };
      const saved = await apiService.createBroadcast(payload as any);
      onSendBroadcast(saved);
      setSendSuccessToast(true);
      setMessageText('');
      setMediaId(''); setMediaName(''); setMediaUrlInput(''); setDetectedNote(''); setMediaError('');
      setSelectedBotIds([]);
      setInlineButtons([]); setPinMessage(false);
      setTimeout(() => {
        setSendSuccessToast(false);
        setIsCreatingNew(false);
      }, 1000);
    } catch (err: any) {
      const msg = err?.response?.data?.error || err?.message || 'Broadcast failed';
      alert(msg);
    } finally {
      setIsSending(false);
    }
  };


  return (
    <div className="space-y-6 pb-12">
      {/* FULL-PAGE VIEW 1: LIVE BROADCAST DETAILS */}
      {selectedBroadcastForDetails ? (
        (() => {
          const bc = selectedBroadcastForDetails;
          const inProgress =
            bc.inProgressCount !== undefined
              ? bc.inProgressCount
              : bc.status === 'Active'
              ? Math.max(0, bc.totalTargetUsers - bc.sentCount)
              : 0;
          const failed =
            bc.failedCount !== undefined
              ? bc.failedCount
              : bc.failedRecipients?.length || 0;
          const progressPct = Math.min(
            100,
            Math.round((bc.sentCount / (bc.totalTargetUsers || 1)) * 100)
          );

          const botStatsList: BotBroadcastStats[] =
            bc.botStats && bc.botStats.length > 0
              ? bc.botStats
              : bc.targetBotUsernames.map((u, i) => {
                  const bId = bc.targetBotIds[i] || `bot-${i}`;
                  const foundBot = bots.find((b) => b.id === bId || b.username === u);
                  const totalPart = Math.round(
                    bc.totalTargetUsers / (bc.targetBotUsernames.length || 1)
                  );
                  const sentPart = Math.round(
                    bc.sentCount / (bc.targetBotUsernames.length || 1)
                  );
                  return {
                    botId: bId,
                    botName: foundBot?.name || u.replace('@', ''),
                    botUsername: u,
                    targetCount: totalPart,
                    sentCount: sentPart,
                    failedCount: Math.round(
                      failed / (bc.targetBotUsernames.length || 1)
                    ),
                    status:
                      bc.status === 'Active'
                        ? 'Delivering'
                        : bc.status === 'Done'
                        ? 'Done'
                        : bc.status === 'Paused'
                        ? 'Paused'
                        : 'Failed',
                    speed: bc.deliverySpeed || '30 msgs/sec',
                  };
                });

          const filteredBotStatsList = botStatsList.filter((b) => {
            const matchesQuery =
              !detailsBotSearch.trim() ||
              b.botName.toLowerCase().includes(detailsBotSearch.toLowerCase()) ||
              b.botUsername.toLowerCase().includes(detailsBotSearch.toLowerCase());
            const matchesStatus =
              detailsBotStatusFilter === 'All' ||
              (detailsBotStatusFilter === 'Delivering' && b.status === 'Delivering') ||
              (detailsBotStatusFilter === 'Done' && b.status === 'Done') ||
              (detailsBotStatusFilter === 'Paused' && b.status === 'Paused') ||
              (detailsBotStatusFilter === 'Cancelled' && b.status === 'Cancelled');
            return matchesQuery && matchesStatus;
          });

          return (
            <div className="space-y-5 animate-in fade-in duration-200">
              {/* TOP NAVIGATION & ACTION CONTROLS */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-3 min-w-0">
                  {/* Top Back Icon Button */}
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedBroadcastForDetails(null);
                      setDetailsBotSearch('');
                      setDetailsBotStatusFilter('All');
                    }}
                    className="p-2 sm:px-3 sm:py-2 rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold text-xs flex items-center gap-1.5 cursor-pointer shadow-xs transition-all shrink-0"
                    title="Back to Campaigns"
                  >
                    <ArrowLeft className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    <span className="font-bold">Back</span>
                  </button>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                        Live Analytics Engine
                      </span>
                      <span className="text-slate-400">•</span>
                      <span className="text-[11px] text-slate-500 font-mono">
                        {bc.createdAt}
                      </span>
                      <span className="text-slate-400">•</span>
                      <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/80 border border-blue-200 dark:border-blue-900/50 text-[11px] font-mono font-bold text-blue-700 dark:text-blue-300">
                        <Hash className="w-3 h-3 text-blue-500" />
                        <span>Track ID: {bc.id}</span>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigator.clipboard.writeText(bc.id);
                            showActionToast(`Copied Track ID: ${bc.id}`);
                          }}
                          className="hover:text-blue-950 dark:hover:text-white p-0.5 cursor-pointer ml-0.5"
                          title="Copy Track ID"
                        >
                          <Copy className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    </div>
                    <h1 className="text-base sm:text-xl font-black text-slate-900 dark:text-white tracking-tight truncate mt-0.5">
                      {bc.title}
                    </h1>
                  </div>
                </div>

                {/* STATUS & ACTIONS */}
                <div className="flex items-center gap-2 self-start sm:self-auto shrink-0 flex-wrap">
                  {/* Status Badge */}
                  <span
                    className={`px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 ${
                      bc.status === 'Active'
                        ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800'
                        : bc.status === 'Done'
                        ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300'
                        : bc.status === 'Paused'
                        ? 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800'
                        : 'bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800'
                    }`}
                  >
                    {bc.status === 'Active' && (
                      <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
                    )}
                    {(bc.status === 'Cancelled' || bc.status === 'Failed') && (
                      <XCircle className="w-3.5 h-3.5 text-rose-500" />
                    )}
                    <span>{bc.status === 'Active' ? 'Delivering Live' : bc.status}</span>
                  </span>

                  {/* Status Action Buttons with Confirmation — only what makes sense for the real status */}
                  {bc.status === 'Done' || bc.status === 'Completed' ? (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 font-bold text-xs border border-emerald-300 dark:border-emerald-800">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      <span>Campaign Completed</span>
                    </div>
                  ) : bc.status === 'Failed' ? (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 font-bold text-xs border border-rose-300 dark:border-rose-800">
                      <AlertCircle className="w-3.5 h-3.5 text-rose-500" />
                      <span>Campaign Failed</span>
                    </div>
                  ) : bc.status === 'Cancelled' ? (
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 font-bold text-xs border border-rose-300 dark:border-rose-800">
                      <XCircle className="w-3.5 h-3.5 text-rose-500" />
                      <span>Campaign Cancelled</span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      {bc.status === 'Active' ? (
                        <button
                          type="button"
                          onClick={() => setActionConfirmModal({ isOpen: true, type: 'pause_campaign', broadcast: bc })}
                          className="px-3.5 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs flex items-center gap-1.5 shadow-md shadow-amber-500/20 transition-all cursor-pointer"
                        >
                          <Pause className="w-3.5 h-3.5" />
                          <span>Pause Campaign</span>
                        </button>
                      ) : bc.status === 'Paused' ? (
                        <button
                          type="button"
                          onClick={() => setActionConfirmModal({ isOpen: true, type: 'resume_campaign', broadcast: bc })}
                          className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs flex items-center gap-1.5 shadow-md shadow-emerald-500/20 transition-all cursor-pointer"
                        >
                          <Play className="w-3.5 h-3.5" />
                          <span>Resume Campaign</span>
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => setActionConfirmModal({ isOpen: true, type: 'cancel_campaign', broadcast: bc })}
                        className="px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold text-xs flex items-center gap-1.5 shadow-md shadow-rose-500/20 transition-all cursor-pointer"
                        title="Cancel this campaign and stop all remaining sends"
                      >
                        <X className="w-3.5 h-3.5" />
                        <span>Cancel Campaign</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* SECTION A: AGGREGATE STATS & AVERAGE TOTALS */}
              <div className="space-y-2.5">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Activity className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300 truncate">
                      Overall Campaign Performance &amp; Totals
                    </h3>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono min-w-0">
                    <label className="flex items-center gap-1.5 min-w-0">
                      <span className="text-slate-400 shrink-0">Speed:</span>
                      <select
                        value={bc.deliverySpeed || '30 msgs/sec'}
                        onChange={(e) => handleUpdateDeliverySpeed(bc, e.target.value)}
                        className="max-w-[min(100%,11rem)] bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-2 py-1 text-[11px] font-bold text-blue-600 dark:text-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-500 cursor-pointer shadow-xs"
                        title="Adjust live broadcast speed"
                      >
                        {[...speedOptions, ...(speedOptions.includes(bc.deliverySpeed || '') ? [] : [bc.deliverySpeed || '30 msgs/sec'])].map((s) => (
                          <option key={s} value={s}>{s === 'Unlimited' ? 'Unlimited (Turbo)' : s}</option>
                        ))}
                        {lockedSpeeds.map((s) => (<option key={s} value={s} disabled>{s} — upgrade plan</option>))}
                      </select>
                    </label>
                    <span className="text-slate-400 truncate">Mode: {bc.parseMode || 'HTML'}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 sm:gap-3.5">
                  {/* 1. Target Audience */}
                  <div className="glass-panel p-3.5 sm:p-4 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-1 shadow-xs">
                    <div className="flex items-center justify-between text-slate-500 text-[11px]">
                      <span className="font-semibold">Target Audience</span>
                      <Users className="w-3.5 h-3.5 text-blue-500" />
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl sm:text-2xl font-black font-mono text-slate-900 dark:text-white">
                        {(bc.totalTargetUsers || 0).toLocaleString()}
                      </span>
                      <span className="text-[11px] text-slate-400">users</span>
                    </div>
                    <div className="flex items-center gap-1 pt-0.5">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300 font-mono truncate">
                        Limit: {bc.targetUserLimit ? `${(bc.targetUserLimit || 0).toLocaleString()} Users` : 'All Users'}
                      </span>
                    </div>
                  </div>

                  {/* 2. Delivered Success */}
                  <div className="glass-panel p-3.5 sm:p-4 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-1 shadow-xs">
                    <div className="flex items-center justify-between text-slate-500 text-[11px]">
                      <span className="font-semibold">Delivered Success</span>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl sm:text-2xl font-black font-mono text-emerald-600 dark:text-emerald-400">
                        {(bc.sentCount || 0).toLocaleString()}
                      </span>
                      <span className="text-[11px] font-bold text-emerald-600/80">({progressPct}%)</span>
                    </div>
                    <div className="w-full bg-slate-200 dark:bg-slate-800 h-1.5 rounded-full overflow-hidden mt-1">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          bc.status === 'Active' ? 'bg-blue-600 animate-pulse' : 'bg-emerald-500'
                        }`}
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  </div>

                  {/* 3. In Progress Buffer */}
                  <div className="glass-panel p-3.5 sm:p-4 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-1 shadow-xs">
                    <div className="flex items-center justify-between text-slate-500 text-[11px]">
                      <span className="font-semibold">In Progress Buffer</span>
                      <Activity className="w-3.5 h-3.5 text-blue-500" />
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl sm:text-2xl font-black font-mono text-blue-600 dark:text-blue-400">
                        {(inProgress || 0).toLocaleString()}
                      </span>
                      <span className="text-[11px] text-slate-400">queued</span>
                    </div>
                    <span className="text-[10px] text-slate-400 block truncate">
                      {inProgress > 0 ? 'Worker dispatching...' : 'Queue completed'}
                    </span>
                  </div>

                  {/* 4. Failed Deliveries */}
                  <div className="glass-panel p-3.5 sm:p-4 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-1 shadow-xs">
                    <div className="flex items-center justify-between text-slate-500 text-[11px]">
                      <span className="font-semibold">Failed Deliveries</span>
                      <AlertCircle className="w-3.5 h-3.5 text-rose-500" />
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span
                        className={`text-xl sm:text-2xl font-black font-mono ${
                          failed > 0
                            ? 'text-rose-600 dark:text-rose-400'
                            : 'text-emerald-600 dark:text-emerald-400'
                        }`}
                      >
                        {failed}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {failed > 0 ? 'errors' : 'clean'}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 block truncate">
                      {failed === 0 ? '100% clean delivery' : (bc.reasons && bc.reasons[0] ? bc.reasons[0].reason : 'See the failed list')}
                    </span>
                  </div>

                  {/* 5. Total Duration Taken / Elapsed Time */}
                  <div className="glass-panel p-3.5 sm:p-4 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-1 shadow-xs col-span-2 sm:col-span-1">
                    <div className="flex items-center justify-between text-slate-500 text-[11px]">
                      <span className="font-semibold">Duration Taken</span>
                      <Clock className="w-3.5 h-3.5 text-blue-500" />
                    </div>
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-xl sm:text-2xl font-black font-mono text-blue-600 dark:text-blue-400">
                        {formatDuration(detailsElapsedSeconds)}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        ({detailsElapsedSeconds}s)
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 block truncate">
                      {bc.status === 'Active' ? 'Live broadcast timer' : 'Total broadcast time'}
                    </span>
                  </div>
                </div>
              </div>

              {/* SECTION B: MULTI-BOT PER-BOT BREAKDOWN (Compact, high-density & responsive) */}
              <div className="space-y-3 pt-1">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                  <div className="flex items-center gap-2">
                    <Bot className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    <h3 className="text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
                      Participating Bots Breakdown ({botStatsList.length} Bots)
                    </h3>
                  </div>

                  {/* Search & Filter Toolbar for Multiple Bots */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="relative">
                      <input
                        type="text"
                        placeholder="Search bot..."
                        value={detailsBotSearch}
                        onChange={(e) => setDetailsBotSearch(e.target.value)}
                        className="pl-7 pr-3 py-1 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-blue-500 w-36 sm:w-44"
                      />
                      <Search className="w-3 h-3 text-slate-400 absolute left-2.5 top-2" />
                    </div>

                    <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800/80 p-0.5 rounded-xl border border-slate-200 dark:border-slate-700">
                      {(['All', 'Delivering', 'Paused', 'Cancelled', 'Done'] as const).map((filter) => (
                        <button
                          key={filter}
                          type="button"
                          onClick={() => setDetailsBotStatusFilter(filter)}
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-bold transition cursor-pointer ${
                            detailsBotStatusFilter === filter
                              ? 'bg-blue-600 text-white shadow-2xs'
                              : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                          }`}
                        >
                          {filter}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {filteredBotStatsList.length === 0 ? (
                  <div className="p-8 rounded-2xl glass-panel text-center border border-slate-200 dark:border-slate-800">
                    <Bot className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
                    <p className="text-xs font-bold text-slate-700 dark:text-slate-300">
                      No participating bots match your search filter
                    </p>
                    <button
                      type="button"
                      onClick={() => {
                        setDetailsBotSearch('');
                        setDetailsBotStatusFilter('All');
                      }}
                      className="mt-2 text-xs font-bold text-blue-600 dark:text-blue-400 hover:underline cursor-pointer"
                    >
                      Clear Filter
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2.5 sm:gap-3">
                    {filteredBotStatsList.map((bot) => {
                      const botProgress = Math.min(
                        100,
                        Math.round((bot.sentCount / (bot.targetCount || 1)) * 100)
                      );
                      const realBot = bots.find((b) => b.id === bot.botId || b.username === bot.botUsername);
                      const isFocus = !!focusBotId && (focusBotId === bot.botId || focusBotId === realBot?.id);
                      return (
                        <div
                          key={bot.botId}
                          className={`glass-panel p-3.5 rounded-2xl border space-y-2.5 shadow-xs transition-all flex flex-col justify-between ${isFocus ? 'border-blue-500 ring-2 ring-blue-500/40 bg-blue-50/40 dark:bg-blue-950/20' : 'border-slate-200 dark:border-slate-800 hover:border-blue-500/40'}`}
                        >
                          {isFocus && (
                            <span className="self-start -mt-1 px-2 py-0.5 rounded-full bg-blue-600 text-white text-[9px] font-black uppercase tracking-wider">This bot</span>
                          )}
                          {/* Bot Mini Header */}
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <BotAvatar src={realBot?.photoUrl} alt={bot.botName} className="w-8 h-8 rounded-xl shrink-0 shadow-2xs" iconClassName="w-4 h-4" />
                              <div className="min-w-0">
                                <h4 className="text-xs font-bold text-slate-900 dark:text-white truncate leading-tight">
                                  {bot.botName}
                                </h4>
                                <span className="text-[10px] font-mono text-blue-600 dark:text-blue-400 truncate block">
                                  {bot.botUsername}
                                </span>
                              </div>
                            </div>

                            <span
                              className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider shrink-0 flex items-center gap-1 ${
                                bot.status === 'Delivering'
                                  ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800'
                                  : bot.status === 'Done'
                                  ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300'
                                  : bot.status === 'Paused'
                                  ? 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800'
                                  : 'bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 border border-rose-300 dark:border-rose-800'
                              }`}
                            >
                              {bot.status === 'Delivering' && (
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                              )}
                              <span>{bot.status}</span>
                            </span>
                          </div>

                          {/* Compact Metrics Row */}
                          <div className="grid grid-cols-3 gap-1 p-2 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200/80 dark:border-slate-800/80 text-center">
                            <div>
                              <span className="text-[9px] font-bold uppercase text-slate-400 block">
                                Target
                              </span>
                              <span className="text-[11px] font-black font-mono text-slate-800 dark:text-slate-200">
                                {(bot.targetCount || 0).toLocaleString()}
                              </span>
                            </div>
                            <div>
                              <span className="text-[9px] font-bold uppercase text-slate-400 block">
                                Sent
                              </span>
                              <span className="text-[11px] font-black font-mono text-emerald-600 dark:text-emerald-400">
                                {(bot.sentCount || 0).toLocaleString()}
                              </span>
                            </div>
                            <div>
                              <span className="text-[9px] font-bold uppercase text-slate-400 block">
                                Failed
                              </span>
                              <span
                                className={`text-[11px] font-black font-mono ${
                                  bot.failedCount > 0
                                    ? 'text-rose-600 dark:text-rose-400'
                                    : 'text-slate-400'
                                }`}
                              >
                                {bot.failedCount || 0}
                              </span>
                            </div>
                          </div>

                          {onOpenBot && realBot && (
                            <button
                              type="button"
                              onClick={() => onOpenBot(realBot.id, bc.title || bc.id)}
                              className="w-full py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-wider text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/50 border border-blue-200 dark:border-blue-900/60 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors cursor-pointer"
                            >
                              Open bot →
                            </button>
                          )}

                          {/* Slim Progress Bar */}
                          <div className="space-y-1">
                            <div className="flex items-center justify-between text-[10px]">
                              <span className="text-slate-500 font-semibold">
                                Progress
                              </span>
                              <span className="font-mono font-bold text-slate-900 dark:text-white">
                                {botProgress}%
                              </span>
                            </div>
                            <div className="w-full bg-slate-200 dark:bg-slate-800 h-1.5 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full transition-all duration-500 ${
                                  bot.status === 'Delivering'
                                    ? 'bg-blue-600 animate-pulse'
                                    : bot.status === 'Cancelled'
                                    ? 'bg-rose-500'
                                    : 'bg-emerald-500'
                                }`}
                                style={{ width: `${botProgress}%` }}
                              />
                            </div>
                            <div className="flex items-center justify-between text-[10px] text-slate-400">
                              <span>{bot.speed || '30/s'}</span>
                              <span>
                                {bot.status === 'Cancelled'
                                  ? 'Cancelled'
                                  : (bot.targetCount || 0) - (bot.sentCount || 0) > 0
                                  ? `${Math.max(0, (bot.targetCount || 0) - (bot.sentCount || 0)).toLocaleString()} left`
                                  : 'Done'}
                              </span>
                            </div>

                            {/* Explicit Elapsed & ETA for Bot */}
                            <div className="flex items-center justify-between text-[10px] pt-1.5 border-t border-slate-100 dark:border-slate-800/60 font-mono text-slate-500">
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3 text-blue-500 shrink-0" />
                                <span>Elapsed: {formatDuration(detailsElapsedSeconds)}</span>
                              </span>
                              <span className="flex items-center gap-1">
                                <span className="font-semibold text-slate-400">ETA:</span>
                                <span
                                  className={
                                    bot.status === 'Delivering'
                                      ? 'text-blue-600 dark:text-blue-400 font-bold'
                                      : 'text-slate-400'
                                  }
                                >
                                  {bot.status === 'Done'
                                    ? 'Finished'
                                    : bot.status === 'Cancelled'
                                    ? 'Stopped'
                                    : bot.status === 'Paused'
                                    ? 'Paused'
                                    : `~${Math.ceil(
                                        Math.max(0, (bot.targetCount || 0) - (bot.sentCount || 0)) /
                                          (parseInt(bot.speed || bc.deliverySpeed || '30', 10) || 30)
                                      )}s`}
                                </span>
                              </span>
                            </div>
                          </div>

                          {/* Bot Broadcast Controls: only Pause / Resume while the campaign is running */}
                          <div className="pt-2 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between gap-1.5 flex-wrap">
                            <span className="text-[10px] font-mono text-slate-500">
                              {bot.status === 'Done' ? (
                                <span className="text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" /> Done
                                </span>
                              ) : bot.status === 'Failed' ? (
                                <span className="text-rose-600 dark:text-rose-400 font-bold flex items-center gap-1">
                                  <XCircle className="w-3 h-3" /> Failed
                                </span>
                              ) : bot.status === 'Cancelled' ? (
                                <span className="text-rose-500 font-bold flex items-center gap-1">
                                  <XCircle className="w-3 h-3" /> Cancelled
                                </span>
                              ) : (
                                <span className="font-semibold text-slate-600 dark:text-slate-400">
                                  {bot.status === 'Delivering' ? 'Delivering' : 'Paused'}
                                </span>
                              )}
                            </span>

                            {(bc.status === 'Active' || bc.status === 'Paused') && (bot.status === 'Delivering' || bot.status === 'Paused') && (
                              <div className="flex items-center gap-1">
                                {bot.status === 'Delivering' ? (
                                  <button
                                    type="button"
                                    onClick={() => setActionConfirmModal({ isOpen: true, type: 'pause_bot', broadcast: bc, botId: bot.botId, botName: bot.botName, botUsername: bot.botUsername })}
                                    className="px-2.5 py-1 rounded-lg bg-amber-100 hover:bg-amber-200 dark:bg-amber-950/60 dark:hover:bg-amber-900/60 text-amber-700 dark:text-amber-300 text-[10px] font-bold flex items-center gap-1 transition-colors cursor-pointer shadow-2xs"
                                    title="Pause this bot's broadcast"
                                  >
                                    <Pause className="w-2.5 h-2.5" />
                                    <span>Pause</span>
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => setActionConfirmModal({ isOpen: true, type: 'resume_bot', broadcast: bc, botId: bot.botId, botName: bot.botName, botUsername: bot.botUsername })}
                                    className="px-2.5 py-1 rounded-lg bg-emerald-100 hover:bg-emerald-200 dark:bg-emerald-950/60 dark:hover:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 text-[10px] font-bold flex items-center gap-1 transition-colors cursor-pointer shadow-2xs"
                                    title="Resume this bot's broadcast"
                                  >
                                    <Play className="w-2.5 h-2.5" />
                                    <span>Resume</span>
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          );
        })()
      ) : !isCreatingNew ? (
        /* VIEW 1: CAMPAIGNS LIST HEADER */
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                Mass Messaging Center
              </span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white tracking-tight flex items-center gap-2.5">
              <span>Broadcast Manager</span>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300">
                {broadcasts.length}
              </span>
            </h1>
            <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400 mt-1">
              Dispatch synchronized announcements, marketing pushes, and updates across your bots simultaneously.
            </p>
          </div>

          <button
            type="button"
            onClick={() => setIsCreatingNew(true)}
            className="px-5 py-2.5 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-lg shadow-blue-500/25 flex items-center gap-2 self-start sm:self-auto cursor-pointer transition-all active:scale-95"
          >
            <Plus className="w-4 h-4" />
            <span>New</span>
          </button>
        </div>
      ) : (
        /* VIEW 2: NEW BROADCAST HEADER */
        <div className="flex items-center justify-between gap-3 pb-3 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsCreatingNew(false)}
              className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <span className="text-[11px] font-bold uppercase text-blue-600 dark:text-blue-400">
                Compose Campaign
              </span>
              <h1 className="text-xl font-black text-slate-900 dark:text-white">
                ← New Broadcast
              </h1>
            </div>
          </div>
        </div>
      )}

      {/* VIEW 1: BROADCAST LIST VIEW */}
      {!selectedBroadcastForDetails && !isCreatingNew && (
        <div className="space-y-4">
          {/* Status Tabs: All, Active, Done, Failed */}
          <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-2">
            {(['All', 'Active', 'Done', 'Failed'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => {
                  setActiveTab(tab);
                  setCurrentPage(1);
                }}
                className={`px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                  activeTab === tab
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                    : 'bg-white dark:bg-slate-800/80 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          {/* Broadcasts List or Empty State */}
          {filteredBroadcasts.length === 0 ? (
            <div className="glass-panel p-16 text-center rounded-3xl space-y-3">
              <div className="w-16 h-16 rounded-3xl bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400 flex items-center justify-center mx-auto text-3xl shadow-md shadow-blue-500/10">
                📡
              </div>
              <h3 className="text-lg font-black text-slate-900 dark:text-white">
                No broadcasts yet
              </h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Tap <strong className="text-blue-600 dark:text-blue-400">New</strong> to send a broadcast to your bot users.
              </p>
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreatingNew(true)}
                  className="px-5 py-2.5 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-md shadow-blue-500/20 inline-flex items-center gap-1.5 cursor-pointer"
                >
                  <Plus className="w-4 h-4" />
                  <span>New Broadcast</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {isTransitioning ? (
                <BroadcastCardsSkeleton count={Math.min(pageSize, 6)} />
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                  {paginatedBroadcasts.map((bc) => {
                  const inProgress = bc.inProgressCount !== undefined
                    ? bc.inProgressCount
                    : (bc.status === 'Active' ? Math.max(0, bc.totalTargetUsers - bc.sentCount) : 0);
                  const failed = bc.failedCount !== undefined
                    ? bc.failedCount
                    : (bc.failedRecipients?.length || 0);
                  const progressPct = Math.min(100, Math.round((bc.sentCount / (bc.totalTargetUsers || 1)) * 100));

                  return (
                    <div
                      key={bc.id}
                      onClick={() => setSelectedBroadcastForDetails(bc)}
                      className="glass-panel p-5 rounded-2xl space-y-3.5 border border-slate-200 dark:border-slate-800 hover:border-blue-500/50 transition-all shadow-xs flex flex-col justify-between cursor-pointer group"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                              bc.status === 'Active'
                                ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border border-emerald-300 dark:border-emerald-800 flex items-center gap-1.5'
                                : bc.status === 'Done'
                                ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400'
                                : bc.status === 'Paused'
                                ? 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-800'
                                : 'bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-400 border border-rose-300 dark:border-rose-800'
                            }`}
                          >
                            {bc.status === 'Active' && (
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                            )}
                            {bc.status === 'Cancelled' && (
                              <XCircle className="w-3 h-3 text-rose-500 inline mr-1" />
                            )}
                            <span>● {bc.status}</span>
                          </span>
                          <span className="text-xs text-slate-400">• {bc.createdAt}</span>
                        </div>

                        {onDeleteBroadcast && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmDeleteBroadcast(bc);
                            }}
                            className="p-1 rounded-lg text-slate-400 hover:text-rose-500 transition-colors cursor-pointer"
                            title="Delete broadcast"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>

                      <h4 className="text-sm font-bold text-slate-900 dark:text-white line-clamp-1 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                        {bc.title}
                      </h4>

                      {/* LIVE METRICS: In Process & Failed Users */}
                      <div className="grid grid-cols-2 gap-2.5 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800/90">
                        {/* Processed / In Progress */}
                        <div className="space-y-1">
                          <div className="flex items-center gap-1 text-[11px] font-bold text-slate-600 dark:text-slate-400">
                            <Activity className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                            <span>{bc.status === 'Active' || bc.status === 'Paused' ? 'In Process' : 'Processed'}</span>
                          </div>
                          <div className="flex items-baseline gap-1">
                            <span className="text-sm font-black font-mono text-slate-900 dark:text-white">
                              {(bc.status === 'Active' || bc.status === 'Paused' ? (inProgress || 0) : (bc.sentCount || 0) + (failed || 0)).toLocaleString()}
                            </span>
                            <span className="text-[10px] text-slate-400 font-semibold">
                              / {(bc.totalTargetUsers || 0).toLocaleString()}
                            </span>
                          </div>
                          <div className="w-full bg-slate-200 dark:bg-slate-800 h-1.5 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                bc.status === 'Active' ? 'bg-blue-600 animate-pulse' : 'bg-emerald-500'
                              }`}
                              style={{ width: `${progressPct}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-slate-400 block font-mono">
                            {(bc.sentCount || 0).toLocaleString()} delivered ({progressPct}%)
                          </span>
                        </div>

                        {/* Failed Count & Clean action */}
                        <div className="space-y-1">
                          <div className="flex items-center gap-1 text-[11px] font-bold text-slate-600 dark:text-slate-400">
                            <AlertCircle className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                            <span>Failed</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span
                              className={`text-sm font-black font-mono ${
                                failed > 0
                                  ? 'text-rose-600 dark:text-rose-400'
                                  : 'text-emerald-600 dark:text-emerald-400'
                              }`}
                            >
                              {failed}
                            </span>
                            {(bc.unreachableCount || 0) > 0 && ['Done', 'Failed', 'Cancelled', 'Completed'].includes(bc.status) ? (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmCleanModal({ isOpen: true, broadcast: bc });
                                }}
                                className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 hover:bg-rose-200 dark:bg-rose-950/80 dark:hover:bg-rose-900 text-rose-700 dark:text-rose-300 transition-colors cursor-pointer"
                                title="Remove users who blocked the bot or deleted Telegram"
                              >
                                Clean {(bc.unreachableCount || 0).toLocaleString()}
                              </button>
                            ) : (bc.cleanedCount || 0) > 0 ? (
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400">
                                Cleaned {(bc.cleanedCount || 0).toLocaleString()}
                              </span>
                            ) : null}
                          </div>
                          <span className="text-[10px] text-slate-400 block truncate">
                            {failed === 0 ? '0 delivery errors' : `${(bc.unreachableCount || 0).toLocaleString()} unreachable · ${Math.max(0, failed - (bc.unreachableCount || 0) - (bc.cleanedCount || 0)).toLocaleString()} other`}
                          </span>
                        </div>
                      </div>

                      {/* Card Footer: Track ID & Live Details button ONLY */}
                      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200 dark:border-slate-800/80 text-[11px] text-slate-500">
                        <div className="flex items-center gap-1.5 font-mono text-[11px]">
                          <Hash className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                          <span className="text-slate-400 font-medium">Track ID:</span>
                          <span className="px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/80 text-blue-700 dark:text-blue-300 font-bold font-mono">
                            {bc.id}
                          </span>
                        </div>

                        <div>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedBroadcastForDetails(bc);
                            }}
                            className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm shadow-blue-500/20"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>Live Details</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

              {/* Broadcasts Pagination Toolbar */}
              {totalPages > 1 && (
                <div className="glass-panel p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500">
                  <div className="flex items-center gap-2">
                    <span>
                      Showing {startIndex + 1}–{Math.min(startIndex + pageSize, filteredBroadcasts.length)} of {filteredBroadcasts.length} campaigns
                    </span>
                    <span className="text-slate-300 dark:text-slate-700">|</span>
                    <span className="text-[11px]">Per page</span>
                    <select
                      value={pageSize}
                      onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                      className="px-2 py-0.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-bold"
                    >
                      {[4, 6, 12, 24, 50, 100, 500, 1000].map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </div>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => handlePageChange(1)}
                      disabled={safePage === 1}
                      className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                      title="First Page"
                    >
                      <ChevronsLeft className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handlePageChange(safePage - 1)}
                      disabled={safePage === 1}
                      className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                      title="Previous Page"
                    >
                      <ChevronLeft className="w-3.5 h-3.5" />
                    </button>
                    <span className="px-2.5 font-mono font-bold text-slate-800 dark:text-slate-200">
                      {safePage} / {totalPages}
                    </span>
                    <button
                      type="button"
                      onClick={() => handlePageChange(safePage + 1)}
                      disabled={safePage === totalPages}
                      className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                      title="Next Page"
                    >
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handlePageChange(totalPages)}
                      disabled={safePage === totalPages}
                      className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                      title="Last Page"
                    >
                      <ChevronsRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* VIEW 2: NEW BROADCAST WORKFLOW (Based on exact user outline) */}
      {!selectedBroadcastForDetails && isCreatingNew && (
        <form onSubmit={handleDispatchBroadcast} className="glass-panel p-6 rounded-3xl space-y-6">
          {/* BOTS SECTION */}
          <div className="space-y-2">
            <label className="block text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
              BOTS
            </label>

            <div className="flex flex-wrap items-center gap-2 p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-800">
              {selectedBotIds.length === 0 ? (
                <span className="text-xs text-slate-500 italic">Tap to choose bots...</span>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {selectedBotIds.map((id) => {
                    const b = bots.find((x) => x.id === id);
                    return (
                      <span
                        key={id}
                        className="px-2.5 py-1 rounded-xl bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300 text-xs font-bold flex items-center gap-1.5"
                      >
                        <Bot className="w-3 h-3" />
                        <span>{b ? b.username : id}</span>
                        <button
                          type="button"
                          onClick={() => b && handleToggleBot(b)}
                          className="hover:text-rose-500 font-bold"
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}

              <button
                type="button"
                onClick={() => setShowSelectBotsModal(true)}
                className="ml-auto px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-sm cursor-pointer transition-colors"
              >
                Choose
              </button>
            </div>
          </div>

          {/* AUDIENCE TARGET LIMIT / USER COUNT SECTION */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="block text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
                AUDIENCE TARGET LIMIT / USER COUNT
              </label>
              <span className="text-[11px] text-slate-400">
                Limit broadcast to specific recipient count
              </span>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  value={targetUserLimitInput}
                  onChange={(e) => setTargetUserLimitInput(e.target.value)}
                  placeholder="e.g. 5000 or All"
                  className="w-full px-4 py-2.5 rounded-2xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-xs font-mono font-bold text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                {['All', '500', '1,000', '5,000', '10,000', '50,000'].map((val) => (
                  <button
                    key={val}
                    type="button"
                    onClick={() => setTargetUserLimitInput(val.replace(',', ''))}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition cursor-pointer ${
                      targetUserLimitInput === val.replace(',', '')
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                    }`}
                  >
                    {val}
                  </button>
                ))}
              </div>
            </div>
            {/* Live selected audience max banner */}
            {selectedBotIds.length > 0 && (
              <div className="p-2.5 rounded-xl bg-blue-50/80 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900/50 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs">
                <span className="text-slate-600 dark:text-slate-300 font-medium">
                  Selected bots active audience pool ceiling:
                </span>
                <span className="font-mono font-bold text-blue-700 dark:text-blue-300 flex items-center gap-1">
                  <Users className="w-3.5 h-3.5 text-blue-500" />
                  {bots
                    .filter((b) => selectedBotIds.includes(b.id))
                    .reduce((sum, b) => sum + (b.activeUsers || 0), 0)
                    .toLocaleString()}{' '}
                  Users Max
                </span>
              </div>
            )}
            <p className="text-[11px] text-slate-500">
              The broadcast engine partitions this target across selected bots. Target is strictly capped to the combined audience pool size.
            </p>
          </div>

          {/* MESSAGE TYPE SECTION */}
          <div className="space-y-2">
            <label className="block text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
              MESSAGE TYPE
            </label>
            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  'Text',
                  'Photo',
                  'Video',
                  'Audio',
                  'Doc',
                  'GIF',
                  'Voice',
                  'VidNote',
                  'Sticker',
                  'Location',
                  'Venue',
                  'Contact',
                  'Poll',
                  'Dice',
                  'Forward',
                ] as const
              ).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => { setMessageType(type); setMediaId(''); setMediaName(''); setMediaError(''); }}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                    messageType === type
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {isDataType && (
            <div className="space-y-3 p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700">
              <label className="block text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">{messageType.toUpperCase()} DETAILS</label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {(DATA_FIELDS[messageType] || []).map((fd) => (
                  <label key={fd.key} className="block text-[11px] font-bold text-slate-500">{fd.label}{fd.req ? ' *' : ''}
                    <input value={dataFields[fd.key] || ''} onChange={(e) => setField(fd.key, e.target.value)} placeholder={fd.ph}
                      className="mt-1 w-full px-3 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                  </label>
                ))}
              </div>
              {messageType === 'Poll' && (
                <div className="space-y-2">
                  <label className="block text-[11px] font-bold text-slate-500">Options (one per line, 2–12) *
                    <textarea rows={4} value={dataFields.options || ''} onChange={(e) => setField('options', e.target.value)} placeholder={'Yes\nNo'}
                      className="mt-1 w-full px-3 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30" />
                  </label>
                  <div className="flex flex-wrap gap-4 text-[11px] font-bold text-slate-600 dark:text-slate-300">
                    <label className="flex items-center gap-1.5"><input type="checkbox" checked={dataFields.anonymous !== 'no'} onChange={(e) => setField('anonymous', e.target.checked ? 'yes' : 'no')} /> Anonymous</label>
                    <label className="flex items-center gap-1.5"><input type="checkbox" checked={dataFields.multiple === 'yes'} onChange={(e) => setField('multiple', e.target.checked ? 'yes' : 'no')} /> Multiple answers</label>
                  </div>
                </div>
              )}
              {messageType === 'Dice' && (
                <div className="flex flex-wrap gap-2">
                  {DICE_EMOJI.map((em) => (
                    <button key={em} type="button" onClick={() => setField('emoji', em)}
                      className={`w-10 h-10 rounded-xl text-xl cursor-pointer border ${((dataFields.emoji || '🎲') === em) ? 'bg-blue-600 border-blue-600' : 'bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700'}`}>{em}</button>
                  ))}
                </div>
              )}
              {messageType === 'Forward' && <p className="text-[11px] text-slate-500">Forwards an existing post to every user. The bot must be able to read that chat.</p>}
              {mediaError && <p role="alert" className="text-[11px] font-bold text-rose-600 dark:text-rose-400">{mediaError}</p>}
            </div>
          )}

          {!isDataType && (<>
          {/* MESSAGE SECTION */}
          <div className="space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <label className="block text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
                  {mediaMode === 'url' ? 'MEDIA LINK' : messageType === 'Text' ? 'MESSAGE' : 'MEDIA & CAPTION'}
                </label>
                <button
                  type="button"
                  title={mediaMode === 'url' ? 'Switch back to normal message / file' : 'Use a link instead (photo, video… detected automatically)'}
                  onClick={() => { setMediaMode((m) => (m === 'url' ? 'file' : 'url')); setMediaError(''); setDetectedNote(''); }}
                  className={`p-1.5 rounded-lg border cursor-pointer transition-colors ${
                    mediaMode === 'url'
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  <Link2 className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Personalize per user tags */}
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] font-bold text-slate-400">Personalize</span>
                {PERSONALIZE_TAGS.map(([tag, hint]) => (
                  <button
                    key={tag}
                    type="button"
                    title={hint}
                    onClick={() => handleInsertTag(tag)}
                    className="px-2 py-0.5 rounded-lg bg-purple-50 dark:bg-purple-950/50 text-purple-700 dark:text-purple-300 hover:bg-purple-100 border border-purple-200 dark:border-purple-800 text-[11px] font-mono font-bold cursor-pointer transition-colors"
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>

            {mediaMode === 'url' && (
              <div className="space-y-1.5">
                <input
                  type="url"
                  value={mediaUrlInput}
                  onChange={(e) => { setMediaUrlInput(e.target.value); setDetectedNote(''); }}
                  onPaste={(e) => { const t = e.clipboardData.getData('text'); if (t) { e.preventDefault(); setMediaUrlInput(t); setTimeout(() => handleDetectUrl(t), 0); } }}
                  onBlur={(e) => { if (e.target.value.trim() && e.target.value.trim() !== lastDetected.current) handleDetectUrl(e.target.value); }}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleDetectUrl((e.target as HTMLInputElement).value); } }}
                  placeholder="Paste a Telegram post link (t.me/channel/123) or a direct photo / video / file link"
                  className="w-full px-4 py-3 rounded-2xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30 shadow-xs"
                />
                <div className="flex items-center gap-2 text-[11px]">
                  {mediaBusy && <span className="text-slate-500">Checking link…</span>}
                  {detectedNote && <span className="px-2 py-0.5 rounded-lg bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 font-bold">{detectedNote}</span>}
                </div>
              </div>
            )}

            {mediaMode === 'file' && messageType !== 'Text' && (
              <div className="space-y-1.5">
                <label className="flex items-center justify-between gap-3 px-4 py-3 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-dashed border-slate-300 dark:border-slate-700 cursor-pointer hover:border-blue-500 transition-colors">
                  <span className="flex items-center gap-2 text-xs font-bold text-slate-700 dark:text-slate-200 min-w-0">
                    <Upload className="w-4 h-4 text-blue-600 shrink-0" />
                    <span className="truncate">{mediaBusy ? 'Uploading…' : mediaName || `Choose ${messageType === 'Doc' ? 'a file' : messageType.toLowerCase()} from your device`}</span>
                  </span>
                  <span className="text-[11px] text-slate-400 shrink-0">max 20 MB</span>
                  <input
                    type="file"
                    accept={ACCEPT_BY_TYPE[messageType] || '*/*'}
                    className="hidden"
                    onChange={(e) => { handlePickMedia(e.target.files?.[0]); e.target.value = ''; }}
                  />
                </label>
              </div>
            )}

            {mediaError && (
              <p role="alert" className="text-[11px] font-bold text-rose-600 dark:text-rose-400">{mediaError}</p>
            )}

            {NO_CAPTION_TYPES.includes(messageType) && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Telegram doesn't allow a caption on {messageType === 'Sticker' ? 'stickers' : 'video notes'}, so only the {messageType === 'Sticker' ? 'sticker' : 'video note'} is sent.
              </p>
            )}

            {!NO_CAPTION_TYPES.includes(messageType) && (mediaMode === 'file' || messageType !== 'Text' || mediaUrlInput) && (
              <textarea
                ref={textareaRef}
                rows={mediaMode === 'url' || messageType !== 'Text' ? 3 : 5}
                required={messageType === 'Text' && mediaMode !== 'url'}
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                placeholder={
                  messageType === 'Text' && mediaMode !== 'url'
                    ? 'Write your message... Use {user_name}, {username}, or {user_id} to personalize for each recipient.'
                    : 'Caption (optional)… you can use {user_name}, {username}, or {user_id}.'
                }
                maxLength={messageType === 'Text' ? 4096 : 1024}
                className="w-full p-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30 shadow-xs"
              />
            )}
            {!NO_CAPTION_TYPES.includes(messageType) && (messageType === 'Text' || messageText.length > 0) && (
              <div className="text-right text-[10px] font-mono text-slate-400">{messageText.length} / {messageType === 'Text' ? 4096 : 1024}</div>
            )}
          </div>
          </>)}

          {/* PARSE MODE SECTION */}
          {!NO_CAPTION_TYPES.includes(messageType) && !isDataType && (
          <div className="space-y-2">
            <label className="block text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
              PARSE MODE
            </label>
            <div className="flex flex-wrap gap-2">
              {(['None', 'HTML', 'Markdown', 'MarkdownV2'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setParseMode(mode)}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                    parseMode === mode
                      ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700'
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
          )}

          {/* INLINE BUTTONS SECTION */}
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <label className="block text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
                  INLINE BUTTONS ({inlineButtons.length})
                </label>
                <p className="text-[11px] text-slate-400">
                  Supports URL, Callback Data, Telegram Mini Apps, Switch Inline Query, and Copy Text
                </p>
              </div>

              {/* Quick Add Presets */}
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => handleAddButton('url')}
                  className="px-2.5 py-1 rounded-xl bg-blue-50 hover:bg-blue-100 dark:bg-blue-950/60 dark:hover:bg-blue-900/60 text-blue-600 dark:text-blue-400 text-xs font-bold flex items-center gap-1 cursor-pointer transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  <span>URL</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleAddButton('callback_data')}
                  className="px-2.5 py-1 rounded-xl bg-purple-50 hover:bg-purple-100 dark:bg-purple-950/60 dark:hover:bg-purple-900/60 text-purple-600 dark:text-purple-400 text-xs font-bold flex items-center gap-1 cursor-pointer transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  <span>Callback</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleAddButton('web_app')}
                  className="px-2.5 py-1 rounded-xl bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/60 dark:hover:bg-emerald-900/60 text-emerald-600 dark:text-emerald-400 text-xs font-bold flex items-center gap-1 cursor-pointer transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  <span>Web App</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleAddButton('switch_inline_query')}
                  className="px-2.5 py-1 rounded-xl bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/60 dark:hover:bg-indigo-900/60 text-indigo-600 dark:text-indigo-400 text-xs font-bold flex items-center gap-1 cursor-pointer transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  <span>Share</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleAddButton('copy_text')}
                  className="px-2.5 py-1 rounded-xl bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/60 dark:hover:bg-amber-900/60 text-amber-600 dark:text-amber-400 text-xs font-bold flex items-center gap-1 cursor-pointer transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  <span>Copy Text</span>
                </button>
              </div>
            </div>

            {inlineButtons.length > 1 && (
              <div className="flex flex-wrap items-center gap-2 text-[11px]">
                <span className="font-bold text-slate-500">Arrange:</span>
                {[1, 2, 3, 4].map((n) => (
                  <button key={n} type="button"
                    onClick={() => setInlineButtons(inlineButtons.map((b, i) => ({ ...b, row: Math.floor(i / n) + 1 })))}
                    className="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-blue-100 dark:hover:bg-blue-950/60 text-slate-700 dark:text-slate-300 font-bold cursor-pointer">
                    {n} per row
                  </button>
                ))}
                <span className="text-slate-400">or set the Row number on each button (same row = side by side)</span>
              </div>
            )}
            {inlineButtons.length > 0 && (
              <div className="p-2.5 rounded-2xl bg-slate-100 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 space-y-1.5">
                {Array.from(new Set(inlineButtons.map((b, i) => b.row || i + 1))).sort((a, b) => a - b).map((r) => (
                  <div key={r} className="flex gap-1.5">
                    {inlineButtons.filter((b, i) => (b.row || i + 1) === r).map((b) => (
                      <div key={b.id} className={`flex-1 truncate text-center px-2 py-1.5 rounded-lg text-[11px] font-bold text-white ${b.style === 'success' ? 'bg-emerald-600' : b.style === 'danger' ? 'bg-red-600' : b.style === 'primary' ? 'bg-blue-600' : 'bg-slate-500'}`}>
                        {b.iconEmojiId ? '✨ ' : ''}{b.text}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            {inlineButtons.length === 0 ? (
              <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-dashed border-slate-300 dark:border-slate-700 text-center">
                <p className="text-xs text-slate-500">
                  No inline buttons added — click any button type above to attach buttons to this broadcast message
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {inlineButtons.map((btn, idx) => {
                  const bType = btn.type || 'url';
                  return (
                    <div
                      key={btn.id}
                      className="p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-800 space-y-2.5"
                    >
                      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
                        {/* Type indicator & selector */}
                        <div className="flex items-center gap-1.5 w-full sm:w-44">
                          <span className="text-[10px] font-mono text-slate-400 shrink-0">
                            #{idx + 1}
                          </span>
                          <select
                            value={bType}
                            onChange={(e) =>
                              handleUpdateButton(btn.id, {
                                type: e.target.value as TelegramButtonType,
                              })
                            }
                            className="w-full px-2.5 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-bold"
                          >
                            <option value="url">URL Link</option>
                            <option value="callback_data">Callback Data</option>
                            <option value="web_app">Telegram Web App</option>
                            <option value="switch_inline_query">Switch Inline Query</option>
                            <option value="copy_text">Copy Text Button</option>
                          </select>
                        </div>

                        {/* Button Label Input */}
                        <input
                          type="text"
                          value={btn.text}
                          onChange={(e) => handleUpdateButton(btn.id, { text: e.target.value })}
                          placeholder="Button label (e.g. Open Portal)"
                          className="flex-1 w-full px-3 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-semibold"
                        />

                        {/* Delete Button */}
                        <button
                          type="button"
                          onClick={() => handleRemoveButton(btn.id)}
                          className="p-1.5 text-slate-400 hover:text-rose-500 cursor-pointer self-end sm:self-auto transition-colors"
                          title="Remove button"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>

                      <div className="pl-0 sm:pl-7 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                        <label className="flex items-center gap-1.5 font-bold text-slate-500">Row
                          <input type="number" min={1} max={20} value={btn.row || idx + 1}
                            onChange={(e) => handleUpdateButton(btn.id, { row: Math.max(1, Math.min(20, Number(e.target.value) || 1)) })}
                            className="w-14 px-2 py-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono" />
                        </label>
                        <label className="flex items-center gap-1.5 font-bold text-slate-500">Colour
                          <select value={btn.style || ''} onChange={(e) => handleUpdateButton(btn.id, { style: (e.target.value || undefined) as any })}
                            className="px-2 py-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white">
                            <option value="">Default</option><option value="primary">Blue</option><option value="success">Green</option><option value="danger">Red</option>
                          </select>
                        </label>
                        <label className="flex items-center gap-1.5 font-bold text-slate-500 col-span-2">Premium emoji ID
                          <input type="text" inputMode="numeric" value={btn.iconEmojiId || ''} placeholder="5368324170671202286"
                            onChange={(e) => handleUpdateButton(btn.id, { iconEmojiId: e.target.value.replace(/\D/g, '').slice(0, 30) })}
                            className="flex-1 min-w-0 px-2 py-1 rounded-lg bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono" />
                        </label>
                      </div>

                      {/* Type-Specific Payload Input */}
                      <div className="pl-0 sm:pl-7">
                        {bType === 'url' && (
                          <div className="flex items-center gap-2">
                            <ExternalLink className="w-3.5 h-3.5 text-blue-500 shrink-0" />
                            <input
                              type="url"
                              value={btn.url || ''}
                              onChange={(e) => handleUpdateButton(btn.id, { url: e.target.value })}
                              placeholder="https://t.me/your_channel or https://example.com"
                              className="w-full px-3 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono"
                            />
                          </div>
                        )}

                        {bType === 'callback_data' && (
                          <div className="flex items-center gap-2">
                            <Terminal className="w-3.5 h-3.5 text-purple-500 shrink-0" />
                            <input
                              type="text"
                              value={btn.callbackData || ''}
                              onChange={(e) =>
                                handleUpdateButton(btn.id, { callbackData: e.target.value })
                              }
                              placeholder="Callback payload string (e.g. vote:candidate_42 or menu:refresh)"
                              className="w-full px-3 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono"
                            />
                          </div>
                        )}

                        {bType === 'web_app' && (
                          <div className="flex items-center gap-2">
                            <Globe className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                            <input
                              type="url"
                              value={btn.webAppUrl || ''}
                              onChange={(e) =>
                                handleUpdateButton(btn.id, { webAppUrl: e.target.value })
                              }
                              placeholder="HTTPS Telegram Mini App URL (e.g. https://miniapp.telebot.org)"
                              className="w-full px-3 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono"
                            />
                          </div>
                        )}

                        {bType === 'switch_inline_query' && (
                          <div className="flex items-center gap-2">
                            <Share2 className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
                            <input
                              type="text"
                              value={btn.switchInlineQuery || ''}
                              onChange={(e) =>
                                handleUpdateButton(btn.id, { switchInlineQuery: e.target.value })
                              }
                              placeholder="Query string inserted into chat (e.g. share_promo_code)"
                              className="w-full px-3 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono"
                            />
                          </div>
                        )}

                        {bType === 'copy_text' && (
                          <div className="flex items-center gap-2">
                            <Copy className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                            <input
                              type="text"
                              value={btn.copyText || ''}
                              onChange={(e) =>
                                handleUpdateButton(btn.id, { copyText: e.target.value })
                              }
                              placeholder="Text copied to user clipboard when pressed (e.g. PROMO2026)"
                              className="w-full px-3 py-1.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono"
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* LANGUAGE FILTER SECTION */}
          <div className="space-y-2">
            <label className="flex items-center gap-1.5 text-xs font-black uppercase tracking-wider text-slate-700 dark:text-slate-300">
              <button type="button" onClick={() => setShowLangs((v) => !v)} title="Which languages your users speak"
                className="p-1 rounded-lg bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 hover:bg-blue-100 cursor-pointer">
                <Languages className="w-3.5 h-3.5" />
              </button>
              LANGUAGE FILTER (optional)
            </label>
            {showLangs && (
              <div className="p-3 rounded-2xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-800 text-[11px]">
                {selectedBotIds.length === 0 ? <span className="text-slate-500">Select a bot first to see its users' languages.</span>
                  : langs.length === 0 ? <span className="text-slate-500">No users yet.</span>
                  : <div className="flex flex-wrap gap-1.5">{langs.map((l) => (
                      <button key={l.code} type="button" onClick={() => setLanguageFilter((v) => Array.from(new Set([...(v ? v.split(/[,\s]+/) : []), l.code].filter(Boolean))).join(', '))}
                        className="px-2 py-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 font-mono font-bold text-slate-700 dark:text-slate-200 cursor-pointer hover:border-blue-500">
                        {l.code} <span className="text-blue-600 dark:text-blue-400">{l.count.toLocaleString()}</span>
                      </button>))}</div>}
              </div>
            )}
            <input
              type="text"
              value={languageFilter}
              onChange={(e) => setLanguageFilter(e.target.value)}
              placeholder="e.g. en, ru, fa — leave blank for all"
              className="w-full px-4 py-2.5 rounded-xl text-xs bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 font-mono"
            />
          </div>

          {/* PIN + SPEED */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className={`flex items-center justify-between gap-3 p-3 rounded-2xl border text-xs ${planLim.pinBroadcast ? 'border-slate-200 dark:border-slate-800 cursor-pointer' : 'border-dashed border-slate-300 dark:border-slate-700 opacity-70'}`}>
              <span className="flex items-center gap-2 font-bold text-slate-700 dark:text-slate-200"><Pin className="w-4 h-4 text-blue-500" />Pin broadcast
                <span className="font-normal text-slate-400">{planLim.pinBroadcast ? 'pins the message in every chat' : `not in ${planName || 'your'} plan`}</span></span>
              <input type="checkbox" disabled={!planLim.pinBroadcast} checked={pinMessage} onChange={(e) => setPinMessage(e.target.checked)} className="w-5 h-5 accent-blue-600" />
            </label>
            <label className="flex items-center justify-between gap-3 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 text-xs">
              <span className="font-bold text-slate-700 dark:text-slate-200">Speed
                <span className="block font-normal text-slate-400">plan limit: {planCap > 30 ? (planCap >= 1000 ? 'Unlimited' : `${planCap}/sec`) : `${planCap}/sec`}</span></span>
              <select value={newSpeed || speedOptions[speedOptions.length - 1] || ''} onChange={(e) => setNewSpeed(e.target.value)}
                className="px-2 py-1.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-bold">
                {speedOptions.map((s) => <option key={s} value={s}>{s === 'Unlimited' ? 'Unlimited (Turbo)' : s}</option>)}
                {lockedSpeeds.map((s) => <option key={s} value={s} disabled>{s} — upgrade plan</option>)}
              </select>
            </label>
          </div>

          {/* Submit Button */}
          <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setIsCreatingNew(false)}
              className="px-5 py-2.5 rounded-2xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 font-bold text-xs cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={isSending}
              className="px-6 py-3 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-xs shadow-lg shadow-blue-500/30 flex items-center gap-2 cursor-pointer transition-all active:scale-95 disabled:opacity-50"
            >
              {isSending ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Dispatching to telegram network...</span>
                </>
              ) : sendSuccessToast ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-300" />
                  <span>Broadcast Dispatched!</span>
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  <span>Send broadcast to bots</span>
                </>
              )}
            </button>
          </div>
        </form>
      )}

      {/* SELECT BOTS MODAL (High-volume architecture for 1,000–2,000 bots) */}
      <AnimatePresence>
        {showSelectBotsModal && (() => {
          const searchLower = botSearchQuery.toLowerCase().trim();
          const searchedBots = bots.filter((b) => {
            if (!searchLower) return true;
            return (
              b.name.toLowerCase().includes(searchLower) ||
              b.username.toLowerCase().includes(searchLower) ||
              (b.botNumericId && String(b.botNumericId).includes(searchLower))
            );
          });

          const eligibleCount = bots.filter((b) => getBotUsers(b) >= minBroadcastUsers).length;
          const underLimitCount = bots.filter((b) => getBotUsers(b) < minBroadcastUsers).length;

          const filteredBots = searchedBots.filter((b) => {
            const uCount = getBotUsers(b);
            if (botModalFilter === 'Eligible') return uCount >= minBroadcastUsers;
            if (botModalFilter === 'UnderLimit') return uCount < minBroadcastUsers;
            if (botModalFilter === 'Selected') return selectedBotIds.includes(b.id);
            if (botModalFilter === 'Working') return b.status === 'working';
            if (botModalFilter === 'Stopped') return b.status !== 'working';
            return true;
          });

          const modalTotalPages = Math.max(1, Math.ceil(filteredBots.length / botModalPageSize));
          const safeModalPage = Math.min(Math.max(1, botModalPage), modalTotalPages);
          const modalStartIndex = (safeModalPage - 1) * botModalPageSize;
          const paginatedModalBots = filteredBots.slice(modalStartIndex, modalStartIndex + botModalPageSize);

          return (
            <div className="fixed inset-0 z-[80] flex items-stretch sm:items-center justify-center p-0 sm:p-4 bg-slate-900/75 backdrop-blur-xs overscroll-none"
              onClick={(e) => { if (e.target === e.currentTarget) setShowSelectBotsModal(false); }}>
              <motion.div
                initial={{ scale: 0.94, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.94, opacity: 0 }}
                className="w-full sm:max-w-2xl h-[100dvh] sm:h-auto sm:max-h-[92vh] bg-white dark:bg-slate-900 rounded-none sm:rounded-3xl p-4 sm:p-6 shadow-2xl border-0 sm:border border-slate-200 dark:border-slate-800 space-y-3 sm:space-y-4 flex flex-col overflow-hidden"
              >
                {/* Modal Top Header */}
                <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
                        Multi-Bot Cluster Dispatch
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300">
                        {selectedBotIds.length} selected
                      </span>
                    </div>
                    <h3 className="text-base sm:text-lg font-black text-slate-900 dark:text-white">
                      Select Broadcast Bots
                    </h3>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleSelectAllEligibleBots}
                      className="px-2.5 py-1 rounded-xl bg-blue-50 dark:bg-blue-950/60 hover:bg-blue-100 text-blue-600 dark:text-blue-400 font-bold text-xs transition-colors cursor-pointer"
                      title={`Select only bots with at least ${minBroadcastUsers} users`}
                    >
                      Select Eligible ({eligibleCount})
                    </button>
                    <button
                      type="button"
                      onClick={handleClearSelectedBots}
                      className="text-xs font-bold text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 px-1.5 py-1"
                    >
                      Clear
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowSelectBotsModal(false)}
                      className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white ml-1 cursor-pointer"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Admin Policy Minimum Limit Banner */}
                <div className="p-3 rounded-2xl bg-gradient-to-r from-blue-50/90 to-indigo-50/70 dark:from-blue-950/40 dark:to-indigo-950/30 border border-blue-200 dark:border-blue-900/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs">
                  <div className="flex items-center gap-2 min-w-0">
                    <ShieldAlert className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
                    <div className="min-w-0">
                      <span className="font-bold text-slate-900 dark:text-white">
                        Admin Policy Requirement:
                      </span>{' '}
                      <span className="text-slate-600 dark:text-slate-300">
                        Bots must have at least{' '}
                        <strong className="text-blue-600 dark:text-blue-400 font-mono font-black">
                          {minBroadcastUsers}
                        </strong>{' '}
                        users to participate in mass broadcasts.
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 self-end sm:self-auto shrink-0">
                    {!isEditingMinUsers ? (
                      <button
                        type="button"
                        onClick={() => {
                          setTempMinUsers(String(minBroadcastUsers));
                          setIsEditingMinUsers(true);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 font-bold text-[11px] border border-slate-200 dark:border-slate-700 shadow-xs hover:border-blue-400 cursor-pointer transition-colors"
                      >
                        Adjust Limit ({minBroadcastUsers})
                      </button>
                    ) : (
                      <div className="flex items-center gap-1">
                        <input
                          type="number"
                          min="1"
                          max="100000"
                          value={tempMinUsers}
                          onChange={(e) => setTempMinUsers(e.target.value)}
                          className="w-16 px-2 py-1 rounded-lg border border-blue-500 text-xs font-mono font-bold bg-white dark:bg-slate-900 text-slate-900 dark:text-white"
                        />
                        <button
                          type="button"
                          onClick={() => handleSaveMinUsers(parseInt(tempMinUsers) || 20)}
                          className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs cursor-pointer"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setIsEditingMinUsers(false)}
                          className="px-1.5 py-1 text-slate-400 hover:text-slate-600 text-xs cursor-pointer"
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Search Bar & Quick Filter Tabs */}
                <div className="space-y-2">
                  <div className="relative">
                    <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      type="text"
                      value={botSearchQuery}
                      onChange={(e) => {
                        setBotSearchQuery(e.target.value);
                        setBotModalPage(1);
                      }}
                      placeholder={`Search across ${bots.length} total bots by name, username, or bot ID…`}
                      className="w-full pl-10 pr-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 font-medium"
                    />
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
                    {/* Filter Tabs */}
                    <div className="flex items-center gap-1 p-0.5 rounded-xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                      {[
                        { id: 'All', label: `All (${searchedBots.length})` },
                        { id: 'Eligible', label: `Eligible (≥${minBroadcastUsers})` },
                        { id: 'Selected', label: `Selected (${selectedBotIds.length})` },
                        { id: 'UnderLimit', label: `Below Limit (<${minBroadcastUsers})` },
                      ].map((tab) => (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => {
                            setBotModalFilter(tab.id as any);
                            setBotModalPage(1);
                          }}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer ${
                            botModalFilter === tab.id
                              ? 'bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-xs'
                              : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    {/* Page Size Selector */}
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                      <span>Per page:</span>
                      <select
                        value={botModalPageSize}
                        onChange={(e) => {
                          setBotModalPageSize(Number(e.target.value));
                          setBotModalPage(1);
                        }}
                        className="px-2 py-0.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-bold"
                      >
                        {[15, 25, 50, 100, 500, 1000].map((sz) => (
                          <option key={sz} value={sz}>{sz}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>

                {/* Paginated Scalable Bots List */}
                <div className="flex-1 overflow-y-auto space-y-2 pr-1 min-h-0 sm:min-h-[220px]">
                  {filteredBots.length === 0 ? (
                    <div className="p-8 text-center text-slate-400">
                      <Bot className="w-8 h-8 mx-auto mb-2 opacity-40" />
                      <p className="text-xs font-bold">No bots match the current criteria</p>
                      <button
                        type="button"
                        onClick={() => {
                          setBotSearchQuery('');
                          setBotModalFilter('All');
                        }}
                        className="mt-2 text-xs text-blue-600 dark:text-blue-400 font-bold hover:underline cursor-pointer"
                      >
                        Reset filters
                      </button>
                    </div>
                  ) : (
                    paginatedModalBots.map((b) => {
                      const isSelected = selectedBotIds.includes(b.id);
                      const userCount = getBotUsers(b);
                      const isEligible = userCount >= minBroadcastUsers;

                      return (
                        <div
                          key={b.id}
                          onClick={() => handleToggleBot(b)}
                          className={`p-3 rounded-2xl border transition-all flex items-center justify-between gap-3 min-w-0 ${
                            !isEligible
                              ? 'bg-slate-50/70 dark:bg-slate-900/40 border-slate-200 dark:border-slate-800/80 opacity-60 cursor-not-allowed'
                              : isSelected
                              ? 'bg-blue-50/90 dark:bg-blue-950/50 border-blue-500 text-blue-950 dark:text-blue-200 cursor-pointer shadow-xs'
                              : 'bg-white dark:bg-slate-800/60 border-slate-200 dark:border-slate-700 hover:border-blue-400/80 cursor-pointer'
                          }`}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center font-bold text-xs shrink-0 shadow-2xs">
                              {b.name.charAt(0) || 'B'}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-xs text-slate-900 dark:text-white truncate block">
                                  {b.name}
                                </span>
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                                  {b.status}
                                </span>
                              </div>
                              <span className="text-[11px] font-mono text-slate-500 truncate block">
                                {b.username}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center gap-2.5 shrink-0">
                            {/* User count badge */}
                            <div
                              className={`flex items-center gap-1 px-2.5 py-1 rounded-xl text-xs font-mono font-bold border ${
                                isEligible
                                  ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                                  : 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                              }`}
                              title={
                                isEligible
                                  ? `Bot has ${userCount} users (meets min requirement of ${minBroadcastUsers})`
                                  : `Bot has ${userCount} users (needs at least ${minBroadcastUsers} users)`
                              }
                            >
                              <Users className="w-3.5 h-3.5" />
                              <span>{userCount.toLocaleString()}</span>
                            </div>

                            {/* Requirement warning or Checkbox */}
                            {!isEligible ? (
                              <div
                                className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300"
                                title={`This bot does not have the minimum required ${minBroadcastUsers} users.`}
                              >
                                <Lock className="w-2.5 h-2.5" />
                                <span>&lt;{minBroadcastUsers} req</span>
                              </div>
                            ) : (
                              <div
                                className={`w-5 h-5 rounded-lg border flex items-center justify-center transition-colors ${
                                  isSelected
                                    ? 'bg-blue-600 border-blue-600 text-white'
                                    : 'border-slate-300 dark:border-slate-600'
                                }`}
                              >
                                {isSelected && <Check className="w-3.5 h-3.5" />}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Pagination Controls */}
                {modalTotalPages > 1 && (
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-xs text-slate-500">
                    <span>
                      Showing {modalStartIndex + 1}–{Math.min(modalStartIndex + botModalPageSize, filteredBots.length)} of {filteredBots.length} bots
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setBotModalPage(1)}
                        disabled={safeModalPage === 1}
                        className="p-1 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                        title="First Page"
                      >
                        <ChevronsLeft className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setBotModalPage(safeModalPage - 1)}
                        disabled={safeModalPage === 1}
                        className="p-1 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                        title="Previous"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <span className="px-2 font-mono font-bold text-slate-800 dark:text-slate-200">
                        {safeModalPage} / {modalTotalPages}
                      </span>
                      <button
                        type="button"
                        onClick={() => setBotModalPage(safeModalPage + 1)}
                        disabled={safeModalPage === modalTotalPages}
                        className="p-1 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                        title="Next"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setBotModalPage(modalTotalPages)}
                        disabled={safeModalPage === modalTotalPages}
                        className="p-1 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                        title="Last Page"
                      >
                        <ChevronsRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                )}

                {/* Modal Footer Confirm */}
                <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowSelectBotsModal(false)}
                    className="w-full py-3 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 transition-colors cursor-pointer flex items-center justify-center gap-2"
                  >
                    <span>Confirm Selection — {selectedBotIds.length} bot{selectedBotIds.length !== 1 ? 's' : ''} selected</span>
                  </button>
                </div>
              </motion.div>
            </div>
          );
        })()}
      </AnimatePresence>

      {/* CONFIRMATION MODAL FOR CAMPAIGN & BOT ACTIONS (CANCEL, PAUSE, RESUME) */}
      <AnimatePresence>
        {actionConfirmModal && (() => {
          const { type, broadcast: bc, botName, botUsername } = actionConfirmModal;
          const isCancel = type === 'cancel_campaign' || type === 'cancel_bot';
          const isPause = type === 'pause_campaign' || type === 'pause_bot';

          const title =
            type === 'cancel_campaign'
              ? 'Cancel Entire Campaign?'
              : type === 'pause_campaign'
              ? 'Pause Campaign Delivery?'
              : type === 'resume_campaign'
              ? 'Resume Campaign Delivery?'
              : type === 'cancel_bot'
              ? 'Cancel Bot Broadcast?'
              : type === 'pause_bot'
              ? 'Pause Bot Broadcast?'
              : 'Resume Bot Broadcast?';

          const description =
            type === 'cancel_campaign'
              ? `Are you sure you want to cancel the entire campaign "${bc.title}"? All remaining message deliveries across all participating bots will be permanently stopped.`
              : type === 'pause_campaign'
              ? `Are you sure you want to pause delivery for campaign "${bc.title}"? Message dispatching will be held until you choose to resume.`
              : type === 'resume_campaign'
              ? `Are you sure you want to resume delivery for campaign "${bc.title}"? Active dispatch workers will proceed delivering queued messages.`
              : type === 'cancel_bot'
              ? `Are you sure you want to cancel broadcast delivery for bot "${botName || 'Selected Bot'}" (${botUsername || ''})? Remaining messages queued for this bot will be stopped.`
              : type === 'pause_bot'
              ? `Are you sure you want to pause broadcast delivery for bot "${botName || 'Selected Bot'}" (${botUsername || ''})? You can resume delivery at any time.`
              : `Are you sure you want to resume broadcast delivery for bot "${botName || 'Selected Bot'}" (${botUsername || ''})? Dispatching to remaining recipients will continue.`;

          const confirmButtonText =
            type === 'cancel_campaign'
              ? 'Yes, Cancel Campaign'
              : type === 'pause_campaign'
              ? 'Yes, Pause Campaign'
              : type === 'resume_campaign'
              ? 'Yes, Resume Campaign'
              : type === 'cancel_bot'
              ? 'Yes, Cancel Bot'
              : type === 'pause_bot'
              ? 'Yes, Pause Bot'
              : 'Yes, Resume Bot';

          const colorTheme = isCancel
            ? {
                bg: 'bg-rose-50 dark:bg-rose-950/60',
                border: 'border-rose-200 dark:border-rose-800',
                text: 'text-rose-600 dark:text-rose-400',
                btnBg: 'bg-rose-600 hover:bg-rose-700 shadow-rose-500/25',
              }
            : isPause
            ? {
                bg: 'bg-amber-50 dark:bg-amber-950/60',
                border: 'border-amber-200 dark:border-amber-800',
                text: 'text-amber-600 dark:text-amber-400',
                btnBg: 'bg-amber-500 hover:bg-amber-600 shadow-amber-500/25',
              }
            : {
                bg: 'bg-emerald-50 dark:bg-emerald-950/60',
                border: 'border-emerald-200 dark:border-emerald-800',
                text: 'text-emerald-600 dark:text-emerald-400',
                btnBg: 'bg-emerald-600 hover:bg-emerald-700 shadow-emerald-500/25',
              };

          return (
            <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs">
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="w-full max-w-md bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-4"
              >
                <div className="flex items-center gap-3">
                  <div className={`p-3 rounded-2xl border ${colorTheme.bg} ${colorTheme.border} ${colorTheme.text} shrink-0`}>
                    {isCancel ? (
                      <XCircle className="w-6 h-6" />
                    ) : isPause ? (
                      <Pause className="w-6 h-6" />
                    ) : (
                      <Play className="w-6 h-6" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-base font-bold text-slate-900 dark:text-white truncate">
                      {title}
                    </h3>
                    <p className="text-xs text-slate-500 truncate">
                      {botName ? `${botName} • ${bc.title}` : bc.title}
                    </p>
                  </div>
                </div>

                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                  {description}
                </p>

                <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setActionConfirmModal(null)}
                    className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer transition-colors"
                  >
                    No, Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleExecuteConfirmedAction}
                    className={`px-5 py-2 rounded-xl text-xs font-bold text-white shadow-md cursor-pointer flex items-center gap-1.5 transition-all ${colorTheme.btnBg}`}
                  >
                    {isCancel ? (
                      <X className="w-3.5 h-3.5" />
                    ) : isPause ? (
                      <Pause className="w-3.5 h-3.5" />
                    ) : (
                      <Play className="w-3.5 h-3.5" />
                    )}
                    <span>{confirmButtonText}</span>
                  </button>
                </div>
              </motion.div>
            </div>
          );
        })()}
      </AnimatePresence>

      {/* CONFIRMATION MODAL FOR CLEANING FAILED USERS */}
      <AnimatePresence>
        {confirmCleanModal && (
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-2xl bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-600 dark:text-rose-400">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    Clean unreachable users?
                  </h3>
                  <p className="text-xs text-slate-500">
                    {confirmCleanModal.broadcast.title}
                  </p>
                </div>
              </div>

              <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                This removes{' '}
                <strong className="text-rose-600 dark:text-rose-400 font-mono">
                  {(confirmCleanModal.broadcast.unreachableCount || 0).toLocaleString()} unreachable user(s)
                </strong>{' '}
                from your audience: people who blocked the bot, deleted their Telegram account, or never started it. Users who failed for any other reason (temporary errors, formatting problems) are kept. Anyone removed who starts the bot again is added back automatically.
              </p>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setConfirmCleanModal(null)}
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => handleConfirmClean(confirmCleanModal.broadcast)}
                  className="px-5 py-2 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white shadow-md shadow-rose-500/20 cursor-pointer flex items-center gap-1.5"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Yes, Confirm & Clean</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* CONFIRMATION MODAL FOR DELETING BROADCAST CAMPAIGN */}
      <AnimatePresence>
        {confirmDeleteBroadcast && (
          <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-md bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-2xl border border-slate-200 dark:border-slate-800 space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-2xl bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-600 dark:text-rose-400">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    Delete Broadcast Campaign?
                  </h3>
                  <p className="text-xs text-slate-500 truncate max-w-xs">
                    {confirmDeleteBroadcast.title}
                  </p>
                </div>
              </div>

              <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                Are you sure you want to permanently delete this broadcast campaign? This action cannot be undone and campaign logs will be removed.
              </p>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setConfirmDeleteBroadcast(null)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (onDeleteBroadcast && confirmDeleteBroadcast) {
                      onDeleteBroadcast(confirmDeleteBroadcast.id);
                      setActionToast(`Deleted campaign "${confirmDeleteBroadcast.title}"`);
                      setTimeout(() => setActionToast(null), 2500);
                      if (selectedBroadcastForDetails?.id === confirmDeleteBroadcast.id) {
                        setSelectedBroadcastForDetails(null);
                      }
                      setConfirmDeleteBroadcast(null);
                    }
                  }}
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white shadow-md shadow-rose-500/20 cursor-pointer flex items-center gap-1.5"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Delete Campaign</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ACTION TOAST */}
      <AnimatePresence>
        {actionToast && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-2xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-xs font-bold shadow-2xl flex items-center gap-2 border border-slate-800 dark:border-slate-200"
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-400 dark:text-emerald-600" />
            <span>{actionToast}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
