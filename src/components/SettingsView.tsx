import { SecurityCenterCard } from './AdminPanels';
import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  User as UserIcon,
  Key,
  Lock,
  ArrowLeftRight,
  Shield,
  CreditCard,
  AlertTriangle,
  Eye,
  EyeOff,
  Copy,
  Check,
  Sparkles,
  CheckCircle2,
  Plus,
  X,
  Sliders,
  LogOut,
  Laptop,
  Smartphone,
  Globe,
  Radio,
  ExternalLink,
  Trash2,
  RefreshCw,
  Send,
  Mail,
  ZapOff,
  Bell,
  Bot,
  AlertCircle,
} from 'lucide-react';
import { User, PlatformSettings, ActiveSessionItem } from '../types';
import {
  getPlatformSettings,
  loadPlatformSettings,
  savePlatformSettings,
} from '../data/platformStore';
import { apiService } from '../services/apiService';
import { ConfirmationModal } from './ConfirmationModal';

interface SettingsViewProps {
  user: User | null;
  onShowToast?: (msg: string) => void;
}

type SettingsTab = 'account' | 'telegram' | 'preferences' | 'password' | 'transfer' | 'security' | 'plan' | 'danger';

const fmtPts = (n: number) => (Math.abs(n) >= 1e7 ? new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 2 }).format(n) : n.toLocaleString());

export const SettingsView: React.FC<SettingsViewProps> = ({ user, onShowToast }) => {
  const [showEmail, setShowEmail] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState<SettingsTab>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('telebot_settings_active_subtab') as SettingsTab;
      if (saved) return saved;
    }
    return 'account';
  });

  useEffect(() => {
    const on = (e: any) => { if (e?.detail) setActiveSubTab(e.detail as SettingsTab); };
    window.addEventListener('bm_settings_tab', on);
    return () => window.removeEventListener('bm_settings_tab', on);
  }, []);

  const handleSelectSubTab = (tab: SettingsTab) => {
    setActiveSubTab(tab);
    if (typeof window !== 'undefined') {
      localStorage.setItem('telebot_settings_active_subtab', tab);
    }
  };

  const [settings, setSettings] = useState<PlatformSettings>(() =>
    getPlatformSettings(user?.email)
  );
  const reloadSettings = () =>
    loadPlatformSettings().then((st) => setSettings({ ...st, email: user?.email || st.email })).catch(() => {});
  useEffect(() => {
    reloadSettings().then(() => setOutgoingLimitInput(getPlatformSettings().outgoingLimit));
    apiService.getPoints().then((p) => {
      setSettings((prev) => ({ ...prev, plan: { ...prev.plan, name: p.plan || prev.plan.name, remainingPoints: p.planPoints ?? p.points, extraPoints: p.extraPoints ?? 0 } }));
    }).catch(() => {});
    apiService.getGlobalAdmins().then((list) => {
      if (Array.isArray(list)) {
        setSettings((prev) => ({ ...prev, globalBotAdmins: list }));
      }
    }).catch(() => {});
  }, []);


  const [broadcastMinLimit, setBroadcastMinLimit] = useState<number>(20);

  useEffect(() => {
    apiService.getBroadcastMinUsers()
      .then((res) => {
        if (res && typeof res.minBroadcastUsers === 'number') {
          setBroadcastMinLimit(res.minBroadcastUsers);
        }
      })
      .catch(() => {});
  }, []);

  const handleSaveBroadcastMinLimit = async () => {
    try {
      await apiService.updateBroadcastMinUsers(broadcastMinLimit);
      showLocalToast(`Broadcast requirement updated: Min ${broadcastMinLimit} users per bot`);
    } catch {
      showLocalToast('Failed to update minimum broadcast requirement');
    }
  };

  const handleToggleEmailNotifications = () => {
    const nextVal = !settings.emailNotifications;
    const updated = { ...settings, emailNotifications: nextVal };
    setSettings(updated);
    savePlatformSettings(updated);
    localStorage.setItem('telebot_email_notifications', String(nextVal));
    showLocalToast(
      nextVal
        ? 'Email Notifications enabled: Receive alerts and updates by email'
        : 'Email Notifications disabled'
    );
  };

  const NOTIF_TYPES: { key: string; label: string; hint: string }[] = [
    { key: 'bots', label: 'Bot events', hint: 'A bot was added, started, stopped or crashed' },
    { key: 'transfers', label: 'Transfers', hint: 'Bot copies sent to you and replies to yours' },
    { key: 'broadcasts', label: 'Broadcasts', hint: 'A campaign finished, failed or was cancelled' },
    { key: 'billing', label: 'Plan & points', hint: 'Plan changes and low or empty points' },
    { key: 'account', label: 'Account', hint: 'Telegram link and other account activity' },
  ];
  const patchSettings = (patch: Record<string, any>, msg: string) => {
    const updated = { ...settings, ...patch };
    setSettings(updated);
    savePlatformSettings(updated);
    showLocalToast(msg);
  };
  const handleToggleDisableAnimations = () => {
    const nextVal = !settings.disableAnimations;
    const updated = { ...settings, disableAnimations: nextVal };
    setSettings(updated);
    savePlatformSettings(updated);
    localStorage.setItem('telebot_disable_animations', String(nextVal));
    // Explicitly guarantee active subtab remains preferences
    localStorage.setItem('telebot_settings_active_subtab', 'preferences');
    setActiveSubTab('preferences');
    window.dispatchEvent(new CustomEvent('telebot_animation_setting_changed', { detail: nextVal }));
    showLocalToast(
      nextVal
        ? 'Disable Animations enabled: Turn off all page transitions'
        : 'Animations restored: Page transitions active'
    );
  };

  // Sync settings when external changes happen
  useEffect(() => {
    const handleUpdate = (e: any) => {
      if (e.detail) {
        setSettings(e.detail);
      }
    };
    window.addEventListener('telebot_settings_updated', handleUpdate);
    return () => window.removeEventListener('telebot_settings_updated', handleUpdate);
  }, []);

  // Feedback toast state
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const showLocalToast = (msg: string) => {
    setToastMsg(msg);
    if (onShowToast) onShowToast(msg);
    setTimeout(() => setToastMsg(null), 3200);
  };

  // 1. ACCOUNT TAB STATE
  const [showApiKey, setShowApiKey] = useState(false);
  const [copiedApiKey, setCopiedApiKey] = useState(false);

  // Slide to new API key interactive slider state
  const [apiSliderVal, setApiSliderVal] = useState(0);
  const [isSlidingApi, setIsSlidingApi] = useState(false);
  const apiSliderRef = useRef<HTMLDivElement>(null);

  const handleCopyApiKey = () => {
    if (!settings.apiKey) {
      showLocalToast('Generate a new key first — for your security it is only shown once.');
      return;
    }
    navigator.clipboard.writeText(settings.apiKey);
    setCopiedApiKey(true);
    showLocalToast('API Key copied to clipboard!');
    setTimeout(() => setCopiedApiKey(false), 2000);
  };

  const handleSlideApiMove = (clientX: number) => {
    if (!apiSliderRef.current) return;
    const rect = apiSliderRef.current.getBoundingClientRect();
    const width = rect.width - 48; // knob width
    const offsetX = Math.max(0, Math.min(clientX - rect.left - 24, width));
    const percent = Math.round((offsetX / width) * 100);
    setApiSliderVal(percent);

    if (percent >= 92) {
      // Completed slide!
      setApiSliderVal(100);
      setIsSlidingApi(false);
      triggerNewApiKey();
    }
  };

  const triggerNewApiKey = async () => {
    try {
      const r = await apiService.regenerateApiKey();
      const updated: PlatformSettings = { ...settings, apiKey: r.apiKey, apiKeyMasked: r.apiKeyMasked || settings.apiKeyMasked, apiKeyCreatedAt: r.apiKeyCreatedAt };
      setSettings(updated);
      setShowApiKey(true);
      showLocalToast(r.warning || 'New API Key generated — copy it now, it will not be shown again.');
    } catch (e: any) {
      showLocalToast(e?.message || 'Could not generate a new API key');
    }
    setTimeout(() => setApiSliderVal(0), 600);
  };

  // 2. TELEGRAM CONNECT TAB STATE (real, through the connect bot)
  const [tg, setTg] = useState<any>(null);
  const [linkInfo, setLinkInfo] = useState<{ code: string; url: string } | null>(null);
  const isTelegramConnected = !!tg?.connected;
  const telegramUsername = tg?.username ? (String(tg.username).startsWith('@') ? tg.username : `@${tg.username}`) : (tg?.firstName || 'Telegram');
  const telegramConnectedAt = tg?.connectedAt ? new Date(tg.connectedAt).toLocaleString('en-US', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false);
  const [testNotificationSent, setTestNotificationSent] = useState(false);
  const [waitingTg, setWaitingTg] = useState(false);

  const refreshTelegram = async () => {
    try {
      const st = await apiService.getTelegramStatus();
      setTg(st);
      if (st.connected) setWaitingTg(false);
      return st;
    } catch { return null; }
  };
  const newLink = async () => {
    try {
      const l = await apiService.createTelegramLinkCode();
      setLinkInfo({ code: l.code, url: l.url });
      return l;
    } catch (e: any) {
      showLocalToast(e?.message || 'Could not create a connection link');
      return null;
    }
  };
  useEffect(() => {
    refreshTelegram().then((st) => { if (st && !st.connected && st.available) newLink(); });
  }, []);
  useEffect(() => {
    if (!waitingTg && !(activeSubTab === 'telegram')) return;
    const t = setInterval(refreshTelegram, 2500);
    return () => clearInterval(t);
  }, [waitingTg, activeSubTab]);

  const connectBotName = tg?.connectBotUsername || '';
  const userUniqueId = linkInfo?.code || '';
  const telegramLink = linkInfo?.url || tg?.connectBotLink || '';

  const handleConnectTelegram = async () => {
    if (!tg?.available) { showLocalToast('Telegram connection is not available right now.'); return; }
    const l = linkInfo || (await newLink());
    if (!l) return;
    window.open(l.url, '_blank', 'noopener,noreferrer');
    setWaitingTg(true);
    showLocalToast('Open Telegram and press START — this page updates by itself.');
  };

  const handleCopyTelegramLink = () => {
    if (!telegramLink) return;
    navigator.clipboard.writeText(telegramLink);
    showLocalToast('Telegram connection link copied to clipboard!');
  };

  const handleCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    showLocalToast(`${label} copied to clipboard!`);
  };

  const telegramNotifs: Record<string, boolean> = {
    botStartStop: true, botTransfers: true, criticalCrashes: true, broadcastReports: true,
    newSubscribers: false, securityAlerts: true, dailyDigest: false, botErrors: true, lowPoints: true, broadcastStarted: false,
    ...(tg?.alerts || {}),
  };

  const handleDisconnectTelegram = async () => {
    try {
      await apiService.disconnectTelegram();
      await refreshTelegram();
      setShowDisconnectConfirm(false);
      newLink();
      showLocalToast('Telegram account disconnected.');
    } catch (e: any) {
      showLocalToast(e?.message || 'Could not disconnect');
    }
  };

  const handleToggleTelegramSetting = async (key: string) => {
    const updated = { ...telegramNotifs, [key]: !telegramNotifs[key] };
    setTg((prev: any) => ({ ...prev, alerts: updated }));
    try {
      await apiService.updateTelegramAlerts(updated);
      showLocalToast(`Telegram alert updated`);
    } catch (e: any) {
      refreshTelegram();
      showLocalToast(e?.message || 'Could not update alert');
    }
  };

  const handleSendTestNotification = async () => {
    try {
      await apiService.sendTelegramTestAlert();
      setTestNotificationSent(true);
      showLocalToast(`Test notification sent to Telegram (${telegramUsername})! Check your app.`);
      setTimeout(() => setTestNotificationSent(false), 4000);
    } catch (e: any) {
      showLocalToast(e?.message || 'Could not send the test notification');
    }
  };

  // 2. PASSWORD TAB STATE
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPassword) {
      showLocalToast('Please enter your current password');
      return;
    }
    if (newPassword.length < 8) {
      showLocalToast('New password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      showLocalToast('Passwords do not match');
      return;
    }
    try {
      await apiService.changePassword(currentPassword, newPassword);
      showLocalToast('Password updated successfully!');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      reloadSettings();
    } catch (err: any) {
      showLocalToast(err?.message || 'Could not update password');
    }
  };

  // 3. TRANSFER TAB STATE
  const [newWhitelistEmail, setNewWhitelistEmail] = useState('');
  const [outgoingLimitInput, setOutgoingLimitInput] = useState(settings.outgoingLimit);
  const [transferAutoSaved, setTransferAutoSaved] = useState(false);

  const handleSelectTransferConfig = (
    val: 'whitelist_auto' | 'whitelist_only' | 'open' | 'disabled'
  ) => {
    const updated = { ...settings, transferConfig: val };
    setSettings(updated);
    savePlatformSettings(updated);
    setTransferAutoSaved(true);
    showLocalToast(`Transfer rule updated: ${val}`);
    setTimeout(() => setTransferAutoSaved(false), 2500);
  };

  const handleAddWhitelist = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = newWhitelistEmail.trim();
    if (!trimmed) return;
    if (settings.senderWhitelist.includes(trimmed)) {
      showLocalToast('This email/handle is already on the whitelist');
      return;
    }
    if (settings.senderWhitelist.length >= 100) {
      showLocalToast('Whitelist limit reached (maximum 100 entries)');
      return;
    }
    const updated = {
      ...settings,
      senderWhitelist: [...settings.senderWhitelist, trimmed],
    };
    setSettings(updated);
    savePlatformSettings(updated);
    setNewWhitelistEmail('');
    showLocalToast(`Added ${trimmed} to sender whitelist`);
  };

  const handleRemoveWhitelist = (emailToRemove: string) => {
    const updated = {
      ...settings,
      senderWhitelist: settings.senderWhitelist.filter((e) => e !== emailToRemove),
    };
    setSettings(updated);
    savePlatformSettings(updated);
    showLocalToast(`Removed ${emailToRemove} from whitelist`);
  };

  const handleSaveOutgoingLimit = () => {
    const updated = { ...settings, outgoingLimit: outgoingLimitInput };
    setSettings(updated);
    savePlatformSettings(updated);
    showLocalToast(`Outgoing limit set to ${outgoingLimitInput} bots per 10 minutes`);
  };

  // Slide to save Outgoing Limit interactive slider state
  const [limitSliderVal, setLimitSliderVal] = useState(0);
  const [isSlidingLimit, setIsSlidingLimit] = useState(false);
  const limitSliderRef = useRef<HTMLDivElement>(null);

  const handleSlideLimitMove = (clientX: number) => {
    if (!limitSliderRef.current) return;
    const rect = limitSliderRef.current.getBoundingClientRect();
    const width = rect.width - 48; // knob width
    const offsetX = Math.max(0, Math.min(clientX - rect.left - 24, width));
    const percent = Math.round((offsetX / width) * 100);
    setLimitSliderVal(percent);

    if (percent >= 92) {
      setLimitSliderVal(100);
      setIsSlidingLimit(false);
      handleSaveOutgoingLimit();
      setTimeout(() => setLimitSliderVal(0), 700);
    }
  };

  // 4. SECURITY TAB STATE
  const [newAdminId, setNewAdminId] = useState('');

  const handleToggleDeletePermission = () => {
    const updated = {
      ...settings,
      allowBotCodeToDeleteBots: !settings.allowBotCodeToDeleteBots,
    };
    setSettings(updated);
    savePlatformSettings(updated);
    showLocalToast(
      updated.allowBotCodeToDeleteBots
        ? 'Enabled: Bot code permitted to delete bots'
        : 'Disabled: Bot code cannot delete bots'
    );
  };

  const handleAddAdmin = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newAdminId.trim();
    if (!trimmed) return;
    if (settings.globalBotAdmins.includes(trimmed)) {
      showLocalToast('This Telegram ID is already an admin');
      return;
    }
    if (settings.globalBotAdmins.length >= 20) {
      showLocalToast('Admin limit reached (maximum 20 admins)');
      return;
    }
    try {
      const list = await apiService.addGlobalAdmin(trimmed);
      const updated: PlatformSettings = { ...settings, globalBotAdmins: Array.isArray(list) ? list : [...settings.globalBotAdmins, trimmed] };
      setSettings(updated);
      savePlatformSettings(updated);
      setNewAdminId('');
      showLocalToast(`Added admin ${trimmed}`);
    } catch (err: any) {
      showLocalToast(err?.message || 'Failed to add admin');
    }
  };

  const handleRemoveAdmin = async (idToRemove: string) => {
    try {
      const list = await apiService.removeGlobalAdmin(idToRemove);
      const updated: PlatformSettings = {
        ...settings,
        globalBotAdmins: Array.isArray(list) ? list : settings.globalBotAdmins.filter((id) => id !== idToRemove),
      };
      setSettings(updated);
      savePlatformSettings(updated);
      showLocalToast(`Removed Admin ID ${idToRemove}`);
    } catch (err: any) {
      showLocalToast(err?.message || 'Failed to remove admin');
    }
  };

  const handleSignOutAllOtherSessions = async () => {
    try {
      await apiService.revokeOtherSessions();
      await reloadSettings();
      showLocalToast('Signed out of all other devices.');
    } catch (e: any) {
      showLocalToast(e?.message || 'Could not sign out other devices');
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    try {
      await apiService.revokeSession(sessionId);
      await reloadSettings();
      showLocalToast('Session revoked');
    } catch (e: any) {
      showLocalToast(e?.message || 'Could not revoke session');
    }
  };

  // 6. DANGER ZONE TAB STATE
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleteSliderVal, setDeleteSliderVal] = useState(0);
  const [isSlidingDelete, setIsSlidingDelete] = useState(false);
  const deleteSliderRef = useRef<HTMLDivElement>(null);

  const handleDeleteSlideMove = (clientX: number) => {
    if (deleteConfirmText !== 'DELETE') return;
    if (!deleteSliderRef.current) return;
    const rect = deleteSliderRef.current.getBoundingClientRect();
    const width = rect.width - 48;
    const offsetX = Math.max(0, Math.min(clientX - rect.left - 24, width));
    const percent = Math.round((offsetX / width) * 100);
    setDeleteSliderVal(percent);

    if (percent >= 92) {
      setDeleteSliderVal(100);
      setIsSlidingDelete(false);
      const pw = window.prompt('Enter your password to delete your account');
      if (!pw) {
        setDeleteSliderVal(0);
        return;
      }
      apiService.deleteAccount(pw).then(() => {
        showLocalToast('Account deleted.');
        setTimeout(() => window.location.reload(), 800);
      }).catch((e: any) => {
        showLocalToast(e?.message || 'Could not delete the account');
        setDeleteSliderVal(0);
      });
    }
  };

  // Mouse & touch handlers for sliders
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (isSlidingApi) handleSlideApiMove(e.clientX);
      if (isSlidingLimit) handleSlideLimitMove(e.clientX);
      if (isSlidingDelete) handleDeleteSlideMove(e.clientX);
    };
    const onTouchMove = (e: TouchEvent) => {
      if (isSlidingApi && e.touches[0]) handleSlideApiMove(e.touches[0].clientX);
      if (isSlidingLimit && e.touches[0]) handleSlideLimitMove(e.touches[0].clientX);
      if (isSlidingDelete && e.touches[0]) handleDeleteSlideMove(e.touches[0].clientX);
    };
    const onMouseUp = () => {
      if (isSlidingApi) {
        setIsSlidingApi(false);
        if (apiSliderVal < 92) setApiSliderVal(0);
      }
      if (isSlidingLimit) {
        setIsSlidingLimit(false);
        if (limitSliderVal < 92) setLimitSliderVal(0);
      }
      if (isSlidingDelete) {
        setIsSlidingDelete(false);
        if (deleteSliderVal < 92) setDeleteSliderVal(0);
      }
    };

    if (isSlidingApi || isSlidingLimit || isSlidingDelete) {
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('touchmove', onTouchMove);
      window.addEventListener('mouseup', onMouseUp);
      window.addEventListener('touchend', onMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('touchend', onMouseUp);
    };
  }, [
    isSlidingApi,
    isSlidingLimit,
    isSlidingDelete,
    apiSliderVal,
    limitSliderVal,
    deleteSliderVal,
    deleteConfirmText,
  ]);

  const navMenuItems = [
    { id: 'account' as SettingsTab, label: 'Account', icon: <UserIcon className="w-4 h-4" /> },
    { id: 'telegram' as SettingsTab, label: 'Telegram Connect', icon: <Send className="w-4 h-4 text-sky-500" /> },
    { id: 'preferences' as SettingsTab, label: 'Preferences', icon: <Sliders className="w-4 h-4" /> },
    { id: 'password' as SettingsTab, label: 'Password', icon: <Lock className="w-4 h-4" /> },
    { id: 'transfer' as SettingsTab, label: 'Transfer', icon: <ArrowLeftRight className="w-4 h-4" /> },
    { id: 'security' as SettingsTab, label: 'Security', icon: <Shield className="w-4 h-4" /> },
    { id: 'plan' as SettingsTab, label: 'Plan', icon: <CreditCard className="w-4 h-4" /> },
    {
      id: 'danger' as SettingsTab,
      label: 'Danger Zone',
      icon: <AlertTriangle className="w-4 h-4 text-rose-500" />,
      isDanger: true,
    },
  ];

  return (
    <div className="space-y-6 pb-16 max-w-5xl mx-auto">
      {/* Toast Notification */}
      <AnimatePresence>
        {toastMsg && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 16 }}
            className="fixed bottom-6 right-6 z-50 bg-slate-900 dark:bg-white text-white dark:text-slate-900 px-4 py-3 rounded-2xl shadow-2xl text-xs font-bold flex items-center gap-2.5 border border-slate-700/40"
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-400 dark:text-emerald-600 shrink-0" />
            <span>{toastMsg}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white tracking-tight">
          Platform Settings
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-1">
          Manage your account credentials, bot transfer configurations, security rules, and active sessions.
        </p>
      </div>

      {/* Layout: Sub-Navigation Menu + Content View */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Navigation Menu (Left Column / Top on mobile) */}
        <div className="lg:col-span-1">
          <div className="glass-panel p-3 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 sticky top-20">
            <div className="text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider px-3 py-2">
              Settings Menu
            </div>
            <nav className="flex lg:flex-col gap-1.5 overflow-x-auto lg:overflow-visible pb-1 lg:pb-0">
              {navMenuItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => handleSelectSubTab(item.id)}
                  className={`flex items-center gap-2.5 px-3.5 py-2.5 rounded-2xl text-xs font-bold transition-all text-left whitespace-nowrap cursor-pointer ${
                    activeSubTab === item.id
                      ? item.isDanger
                        ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30 font-extrabold shadow-xs'
                        : 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                      : item.isDanger
                      ? 'text-rose-600 dark:text-rose-400 hover:bg-rose-500/10'
                      : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800/60'
                  }`}
                >
                  <span className="shrink-0">{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </nav>
          </div>
        </div>

        {/* Content Pane (Right Column) */}
        <div className="lg:col-span-3 space-y-6">
          {/* TAB 1: ACCOUNT */}
          {activeSubTab === 'account' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <UserIcon className="w-5 h-5 text-blue-500" />
                    Account Information
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Primary email address and master API authentication tokens.
                  </p>
                </div>

                {/* User's Gmail */}
                <div className="space-y-2">
                  <label className="block text-xs font-bold text-slate-700 dark:text-slate-300">
                    User Email (Gmail)
                  </label>
                  <div className="p-3.5 rounded-2xl bg-slate-100/90 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 text-slate-900 dark:text-white text-xs font-mono flex items-center justify-between">
                    <span className="font-semibold truncate min-w-0">
                      {showEmail ? settings.email : (() => { const [a, d] = String(settings.email || '').split('@'); return `${(a || '').slice(0, 1)}${'•'.repeat(Math.max(3, (a || '').length - 1))}@${d || ''}`; })()}
                    </span>
                    <button type="button" onClick={() => setShowEmail((v) => !v)} title={showEmail ? 'Hide email' : 'Show email'} className="ml-2 p-1 text-slate-500 hover:text-slate-800 dark:hover:text-white cursor-pointer shrink-0">
                      {showEmail ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    </button>
                    <button type="button" onClick={() => { try { navigator.clipboard.writeText(settings.email || ''); } catch {} onShowToast?.('Email copied'); }} title="Copy email" className="mr-2 p-1 text-slate-500 hover:text-slate-800 dark:hover:text-white cursor-pointer shrink-0">
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                    <span className="text-[10px] shrink-0 px-2.5 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400 font-sans font-bold">
                      Verified
                    </span>
                  </div>
                </div>

                {/* API Key Box */}
                <div className="space-y-2 pt-2 border-t border-slate-200/70 dark:border-slate-800/70">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300">
                      API Key
                    </label>
                    <span className="text-[10px] text-slate-400">
                      Created: {settings.apiKeyCreatedAt}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 sm:gap-2 w-full min-w-0 max-w-full">
                    <div className="flex-1 min-w-0 p-3 rounded-2xl bg-slate-100/90 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 flex items-center justify-between font-mono text-xs overflow-hidden">
                      <span className="truncate select-all text-slate-900 dark:text-slate-100 block min-w-0 w-full">
                        {settings.apiKey
                          ? (showApiKey ? settings.apiKey : `${settings.apiKey.slice(0, 10)}${'•'.repeat(24)}`)
                          : (settings.apiKeyMasked || 'No API key yet — generate one below')}
                      </span>
                    </div>

                    {/* Eye toggle icon — only meaningful right after generating a key: for security
                        the server never stores or re-sends the raw key, so there is nothing to reveal
                        once the page is reloaded (same model as a GitHub personal access token). */}
                    <button
                      type="button"
                      disabled={!settings.apiKey}
                      onClick={() => setShowApiKey(!showApiKey)}
                      title={!settings.apiKey ? 'Generate a new key to view it (shown once)' : showApiKey ? 'Hide API Key' : 'Show API Key'}
                      className="p-3 rounded-2xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 cursor-pointer transition-colors shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {showApiKey ? (
                        <EyeOff className="w-4 h-4 text-slate-600 dark:text-slate-400" />
                      ) : (
                        <Eye className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                      )}
                    </button>

                    {/* Copy icon */}
                    <button
                      type="button"
                      onClick={handleCopyApiKey}
                      title="Copy API Key"
                      className="p-3 rounded-2xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 cursor-pointer transition-colors shrink-0"
                    >
                      {copiedApiKey ? (
                        <Check className="w-4 h-4 text-emerald-500" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* "Slide to new API key" Slider Button */}
                <div className="space-y-2 pt-4">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-bold text-slate-700 dark:text-slate-300">
                      Regenerate API Key
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Slide fully across to confirm
                    </span>
                  </div>

                  <div
                    ref={apiSliderRef}
                    className="relative w-full h-14 rounded-2xl bg-slate-100 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 overflow-hidden select-none p-1 flex items-center shadow-inner"
                  >
                    {/* Fill track */}
                    <div
                      className="absolute left-0 top-0 bottom-0 bg-gradient-to-r from-blue-600/40 to-indigo-600/40 transition-all"
                      style={{ width: `${apiSliderVal}%` }}
                    />

                    {/* Center guide text - placed cleanly so it never collides with the knob */}
                    <div
                      className="absolute inset-y-0 left-14 right-3 flex items-center justify-center pointer-events-none text-[11px] sm:text-xs font-bold text-slate-500 dark:text-slate-400 tracking-tight sm:tracking-wide text-center truncate transition-opacity"
                      style={{ opacity: Math.max(0, 1 - apiSliderVal / 45) }}
                    >
                      {apiSliderVal >= 90 ? 'Release to regenerate!' : 'Slide to new API key →'}
                    </div>

                    {/* Slider draggable knob */}
                    <div
                      onMouseDown={() => setIsSlidingApi(true)}
                      onTouchStart={() => setIsSlidingApi(true)}
                      style={{
                        transform: `translateX(${(apiSliderVal / 100) * ((apiSliderRef.current?.offsetWidth || 300) - 56)}px)`,
                      }}
                      className="relative z-10 w-12 h-12 rounded-xl bg-blue-600 hover:bg-blue-700 text-white flex items-center justify-center cursor-grab active:cursor-grabbing shadow-md shadow-blue-500/30 transition-transform duration-75"
                    >
                      <Sparkles className="w-5 h-5" />
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* TAB: TELEGRAM CONNECT */}
          {activeSubTab === 'telegram' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              {/* Main Telegram Connection Box (Compact & Clean) */}
              <div className="glass-panel p-4 sm:p-5 rounded-2xl border border-slate-200/80 dark:border-slate-800/80 space-y-4 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-sky-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />

                {/* Top Header Row with Status and Disconnect (if connected) */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200/80 dark:border-slate-800/80 relative z-10">
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      <Send className="w-4 h-4 text-sky-500 shrink-0" />
                      <span>Telegram Connect</span>
                    </h3>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                      Link your account to receive live alerts and push notifications.
                    </p>
                  </div>

                  {/* Status Indicator & Top Disconnect Action */}
                  <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
                    {isTelegramConnected ? (
                      <>
                        <span className="px-2.5 py-1 rounded-xl text-[11px] font-bold bg-emerald-100 dark:bg-emerald-950/80 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 flex items-center gap-1.5 shadow-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          <span>Connected</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => setShowDisconnectConfirm(true)}
                          className="px-3 py-1 rounded-xl bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 dark:hover:bg-rose-900/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900/50 text-[11px] font-bold transition-colors cursor-pointer"
                        >
                          Disconnect
                        </button>
                      </>
                    ) : (
                      <span className="px-2.5 py-1 rounded-xl text-[11px] font-bold bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800 flex items-center gap-1.5 shadow-xs">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                        <span>Not Connected</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Body: Connected State vs Not Connected State */}
                {isTelegramConnected ? (
                  <div className="space-y-3 relative z-10">
                    <div className="p-3.5 rounded-xl bg-gradient-to-r from-sky-500/10 via-blue-500/5 to-transparent border border-sky-200/80 dark:border-sky-900/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-9 h-9 rounded-xl bg-sky-500 text-white flex items-center justify-center shadow-xs shrink-0">
                          <Send className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-slate-900 dark:text-white truncate">
                              {telegramUsername}
                            </span>
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 font-semibold flex items-center gap-1 shrink-0">
                              <Check className="w-2.5 h-2.5" />
                              <span>Live Routing</span>
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 break-words mt-0.5">
                            Linked on {telegramConnectedAt}{tg?.telegramId ? ` • ID ${tg.telegramId}` : ''}{tg?.account ? ` • ${tg.account.plan} • ${tg.account.points.toLocaleString()} pts • ${tg.account.botsRunning}/${tg.account.botsTotal} bots running` : ''}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0 flex-wrap">
                        <button
                          type="button"
                          onClick={handleCopyTelegramLink}
                          className="px-2.5 py-1.5 rounded-lg bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-300 dark:border-slate-700 text-[11px] font-bold flex items-center gap-1 transition-all cursor-pointer shadow-xs"
                          title="Copy connection link"
                        >
                          <Copy className="w-3 h-3" />
                          <span>Copy Link</span>
                        </button>

                        <button
                          type="button"
                          onClick={handleSendTestNotification}
                          className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-[11px] font-bold flex items-center gap-1.5 shadow-xs transition-all cursor-pointer"
                        >
                          <Send className="w-3 h-3" />
                          <span>Send Test Notification</span>
                        </button>
                      </div>
                    </div>

                    {/* Test notification feedback preview banner */}
                    {testNotificationSent && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="p-3 rounded-xl bg-slate-900 text-white dark:bg-slate-950 border border-sky-500/40 shadow-md space-y-1.5 text-xs font-mono"
                      >
                        <div className="flex items-center justify-between border-b border-slate-800 pb-1 text-sky-400 font-bold text-[11px]">
                          <span>🔔 TELEGRAM PREVIEW ({telegramUsername})</span>
                          <span className="text-[10px] text-slate-400">Just now</span>
                        </div>
                        <p className="text-slate-200 text-[11px]">
                          <strong>BOT MATRIX ALERT</strong> System operational! Test notification routing verified.
                        </p>
                      </motion.div>
                    )}
                  </div>
                ) : (
                  /* Not Connected State (Compact, Sleek, Clean) */
                  <div className="space-y-3 relative z-10">
                    <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-800 space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Bot className="w-4 h-4 text-sky-500" />
                          <span className="text-xs font-bold text-slate-900 dark:text-white">
                            Telegram Connect Bot
                          </span>
                          <span className="text-[11px] font-mono text-sky-600 dark:text-sky-400 font-bold">
                            {connectBotName}
                          </span>
                        </div>

                        {/* Account Connect ID badge */}
                        <div className="flex items-center gap-1.5 self-start sm:self-auto bg-white dark:bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700/80 text-[11px]">
                          <span className="text-slate-400 font-medium">Connect ID:</span>
                          <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                            {userUniqueId}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleCopy(userUniqueId, 'Account Connect ID')}
                            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 ml-0.5 cursor-pointer"
                            title="Copy Connect ID"
                          >
                            <Copy className="w-3 h-3" />
                          </button>
                        </div>
                      </div>

                      {/* Breadcrumbs referral link style */}
                      <div className="flex items-center gap-1 text-[11px] flex-wrap">
                        <span className="text-slate-400">Crumbs:</span>
                        <span className="px-2 py-0.5 rounded bg-white dark:bg-slate-900 font-mono text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
                          t.me
                        </span>
                        <span className="text-slate-400">›</span>
                        <span className="px-2 py-0.5 rounded bg-sky-50 dark:bg-sky-950/60 font-mono font-bold text-sky-600 dark:text-sky-400 border border-sky-200/60 dark:border-sky-900/40">
                          {connectBotName.replace('@', '')}
                        </span>
                        <span className="text-slate-400">›</span>
                        <span className="px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-950/60 font-mono text-amber-600 dark:text-amber-400 border border-amber-200/60 dark:border-amber-900/40">
                          ?start={userUniqueId}
                        </span>
                      </div>

                      {/* Full connection URL box & action buttons */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pt-1">
                        <div className="font-mono text-[11px] text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-900/80 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700/80 flex-1 truncate select-all">
                          {telegramLink}
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <button
                            type="button"
                            onClick={handleCopyTelegramLink}
                            className="px-3 py-2 rounded-lg bg-white dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 text-xs font-bold flex items-center gap-1.5 transition-colors cursor-pointer shadow-xs"
                          >
                            <Copy className="w-3.5 h-3.5" />
                            <span>Copy Link</span>
                          </button>

                          <button
                            type="button"
                            onClick={handleConnectTelegram}
                            className="px-3.5 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold flex items-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                          >
                            <Send className="w-3.5 h-3.5" />
                            <span>Connect Telegram</span>
                            <ExternalLink className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Telegram Alert Routing Rules Card - Shown ONLY after connecting */}
              {isTelegramConnected && (
                <div className="glass-panel p-4 sm:p-5 rounded-2xl border border-slate-200/80 dark:border-slate-800/80 space-y-3.5">
                  <div>
                    <h3 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider flex items-center gap-2">
                      <Bell className="w-4 h-4 text-sky-500" />
                      <span>Telegram Alert Routing Rules</span>
                    </h3>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                      Configure which triggers and events send push alerts to your Telegram account.
                    </p>
                  </div>

                  <div className="divide-y divide-slate-100 dark:divide-slate-800/80 space-y-2.5">
                  {/* 1. Bot Start & Stop */}
                  <div className="pt-2 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Bot Start &amp; Stop Alerts
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.botStartStop
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.botStartStop ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Instant notification when any of your bots starts, stops, or restarts
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.botStartStop}
                      onClick={() => handleToggleTelegramSetting('botStartStop')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.botStartStop ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.botStartStop ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* 2. Bot Transfers */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Bot Transfer Notifications
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.botTransfers
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.botTransfers ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Get notified when bots are transferred to or from your account
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.botTransfers}
                      onClick={() => handleToggleTelegramSetting('botTransfers')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.botTransfers ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.botTransfers ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* 3. Downtime & Critical Crashes */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Downtime &amp; Crash Alerts
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.criticalCrashes
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.criticalCrashes ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Receive immediate high-priority emergency alerts if a bot script throws an uncaught error
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.criticalCrashes}
                      onClick={() => handleToggleTelegramSetting('criticalCrashes')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.criticalCrashes ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.criticalCrashes ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* 4. Broadcast Campaign Reports */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Broadcast Campaign Summaries
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.broadcastReports
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.broadcastReports ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Receive a completion report after broadcast runs (sent count, delivery speed, cleaned users)
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.broadcastReports}
                      onClick={() => handleToggleTelegramSetting('broadcastReports')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.broadcastReports ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.broadcastReports ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* 5. New Audience & Subscribers */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          New User &amp; Audience Pings
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.newSubscribers
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.newSubscribers ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Ping when a new Telegram user runs /start or joins your bot's database
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.newSubscribers}
                      onClick={() => handleToggleTelegramSetting('newSubscribers')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.newSubscribers ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.newSubscribers ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* 6. Security Alerts */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Security &amp; Login Alerts
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.securityAlerts
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.securityAlerts ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Instant 2FA and login alerts whenever an account session is initiated or API keys are updated
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.securityAlerts}
                      onClick={() => handleToggleTelegramSetting('securityAlerts')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.securityAlerts ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.securityAlerts ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* 7. Daily Telemetry Digest */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Daily Telemetry &amp; Metrics Digest
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.dailyDigest
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.dailyDigest ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Receive a morning summary of active bot users, total commands triggered, and cluster performance
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.dailyDigest}
                      onClick={() => handleToggleTelegramSetting('dailyDigest')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.dailyDigest ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.dailyDigest ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                  {/* 8. Bot Error Alerts */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Bot Error Alerts
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.botErrors
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.botErrors ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Get told when one of your bots hits an error (at most once every 10 minutes per bot)
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.botErrors}
                      onClick={() => handleToggleTelegramSetting('botErrors')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.botErrors ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.botErrors ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                  {/* 9. Low Points Warning */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Low Points Warning
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.lowPoints
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.lowPoints ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        A heads-up when your points are almost used up, before your bots stop
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.lowPoints}
                      onClick={() => handleToggleTelegramSetting('lowPoints')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.lowPoints ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.lowPoints ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                  {/* 10. Broadcast Started */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          Broadcast Started
                        </span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            telegramNotifs.broadcastStarted
                              ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          {telegramNotifs.broadcastStarted ? 'Active' : 'Muted'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Get a message the moment one of your broadcasts begins sending
                      </p>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={telegramNotifs.broadcastStarted}
                      onClick={() => handleToggleTelegramSetting('broadcastStarted')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                        telegramNotifs.broadcastStarted ? 'bg-sky-600' : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          telegramNotifs.broadcastStarted ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>
              </div>
            )}
            </motion.div>
          )}

          {/* TAB: PREFERENCES */}
          {activeSubTab === 'preferences' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 space-y-5">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <Sliders className="w-5 h-5 text-blue-500" />
                    Preferences & Alerts
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    Manage email delivery and UI transition animation preferences.
                  </p>
                </div>

                <div className="divide-y divide-slate-100 dark:divide-slate-800/80 space-y-4">
                  {/* Email Notifications */}
                  <div className="pt-2 flex items-center justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="p-2.5 rounded-2xl bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400 mt-0.5 shrink-0 border border-blue-200/50 dark:border-blue-800/50">
                        <Mail className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900 dark:text-white">
                            Email Notifications
                          </span>
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                              settings.emailNotifications
                                ? 'bg-emerald-100 dark:bg-emerald-950/80 text-emerald-600 dark:text-emerald-400'
                                : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                            }`}
                          >
                            {settings.emailNotifications ? 'Active' : 'Disabled'}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                          Receive alerts and updates by email
                        </p>
                      </div>
                    </div>

                    <button
                      id="pref-toggle-email-notifications-btn"
                      type="button"
                      role="switch"
                      aria-checked={settings.emailNotifications}
                      onClick={handleToggleEmailNotifications}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
                        settings.emailNotifications
                          ? 'bg-blue-600'
                          : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                          settings.emailNotifications ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* In-app notifications: master switch, browser pop-ups and per-type switches */}
                  <div className="pt-4 space-y-4">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <span className="text-sm font-bold text-slate-900 dark:text-white">Notifications</span>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Turn all in-app notifications on or off. While off, new events are not saved.</p>
                      </div>
                      <button id="pref-toggle-notifications-btn" type="button" role="switch" aria-checked={settings.notificationsEnabled !== false} onClick={() => patchSettings({ notificationsEnabled: settings.notificationsEnabled === false }, settings.notificationsEnabled === false ? 'Notifications turned on' : 'Notifications turned off')}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${settings.notificationsEnabled !== false ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
                      <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${settings.notificationsEnabled !== false ? 'translate-x-5' : 'translate-x-0'}`} />
                    </button>
                    </div>
                    {settings.notificationsEnabled !== false && (
                      <>
                        <div className="flex items-center justify-between gap-4 pl-3 border-l-2 border-slate-100 dark:border-slate-800">
                          <div>
                            <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">Browser pop-ups</span>
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Show a pop-up on this device when something new arrives (once per notification).</p>
                          </div>
                          <button id="pref-toggle-popups-btn" type="button" role="switch" aria-checked={settings.browserPopups !== false} onClick={() => { const on = settings.browserPopups === false; if (on && 'Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {}); patchSettings({ browserPopups: on }, on ? 'Browser pop-ups turned on' : 'Browser pop-ups turned off'); }}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${settings.browserPopups !== false ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
                      <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${settings.browserPopups !== false ? 'translate-x-5' : 'translate-x-0'}`} />
                    </button>
                        </div>
                        {NOTIF_TYPES.map((t) => {
                          const on = (settings.notificationTypes || {})[t.key] !== false;
                          return (
                            <div key={t.key} className="flex items-center justify-between gap-4 pl-3 border-l-2 border-slate-100 dark:border-slate-800">
                              <div>
                                <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{t.label}</span>
                                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{t.hint}</p>
                              </div>
                              <button type="button" role="switch" aria-checked={on} id={`pref-toggle-type-${t.key}`}
                                onClick={() => patchSettings({ notificationTypes: { ...(settings.notificationTypes || {}), [t.key]: !on } }, `${t.label} notifications ${on ? 'turned off' : 'turned on'}`)}
                                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${on ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
                                <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ${on ? 'translate-x-5' : 'translate-x-0'}`} />
                              </button>
                            </div>
                          );
                        })}
                      </>
                    )}
                  </div>

                  {/* Disable Animations */}
                  <div className="pt-4 flex items-center justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="p-2.5 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0 border border-indigo-200/50 dark:border-indigo-800/50">
                        <ZapOff className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900 dark:text-white">
                            Disable Animations
                          </span>
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                              settings.disableAnimations
                                ? 'bg-amber-100 dark:bg-amber-950/80 text-amber-700 dark:text-amber-400'
                                : 'bg-slate-200 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                            }`}
                          >
                            {settings.disableAnimations ? 'Turned Off' : 'Animations Active'}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                          Turn off all page transitions
                        </p>
                      </div>
                    </div>

                    <button
                      id="pref-toggle-disable-animations-btn"
                      type="button"
                      role="switch"
                      aria-checked={settings.disableAnimations}
                      onClick={handleToggleDisableAnimations}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
                        settings.disableAnimations
                          ? 'bg-blue-600'
                          : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                          settings.disableAnimations ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>

                  {/* Broadcast Minimum Audience Policy (Admin Limit) */}
                  <div className="pt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="flex items-start gap-3">
                      <div className="p-2.5 rounded-2xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 mt-0.5 shrink-0 border border-indigo-200/50 dark:border-indigo-800/50">
                        <Radio className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-slate-900 dark:text-white">
                            Minimum Broadcast Users Limit
                          </span>
                          <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300">
                            Admin Policy
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 max-w-md">
                          Minimum registered members/subscribers a bot must have to qualify for mass broadcast campaigns. Default: 20 users.
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                      <input
                        type="number"
                        min="1"
                        max="100000"
                        value={broadcastMinLimit}
                        onChange={(e) => setBroadcastMinLimit(Math.max(1, parseInt(e.target.value) || 1))}
                        className="w-20 px-3 py-1.5 rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-mono font-bold text-slate-900 dark:text-white text-center focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                      />
                      <button
                        type="button"
                        onClick={handleSaveBroadcastMinLimit}
                        className="px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-xs cursor-pointer transition-colors"
                      >
                        Save Policy
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* TAB 2: PASSWORD */}
          {activeSubTab === 'password' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 space-y-5">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <Lock className="w-5 h-5 text-indigo-500" />
                    Change Password
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Update your account password for secure access to BOT MATRIX.
                  </p>
                </div>

                <form onSubmit={handleUpdatePassword} className="space-y-4 max-w-md">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                      Current Password
                    </label>
                    <div className="relative">
                      <input
                        type={showCurrentPw ? 'text' : 'password'}
                        value={currentPassword}
                        onChange={(e) => setCurrentPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full px-3.5 py-2.5 pr-10 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                      />
                      <button
                        type="button"
                        onClick={() => setShowCurrentPw(!showCurrentPw)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                      >
                        {showCurrentPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                      New Password
                    </label>
                    <div className="relative">
                      <input
                        type={showNewPw ? 'text' : 'password'}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full px-3.5 py-2.5 pr-10 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPw(!showNewPw)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
                      >
                        {showNewPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300 mb-1.5">
                      Confirm New Password
                    </label>
                    <input
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full px-3.5 py-2.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                    />
                  </div>

                  <button
                    type="submit"
                    className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 transition-colors cursor-pointer"
                  >
                    Update Password
                  </button>
                </form>
              </div>
            </motion.div>
          )}

          {/* TAB 3: TRANSFER */}
          {activeSubTab === 'transfer' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              {/* Transfer Configuration (Auto-save on select) */}
              <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
                  <div>
                    <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      <ArrowLeftRight className="w-5 h-5 text-blue-500" />
                      Bot Transfer Configuration
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Configure how your account handles incoming transfers. Changes save automatically.
                    </p>
                  </div>
                  {transferAutoSaved && (
                    <span className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Auto-saved
                    </span>
                  )}
                </div>

                <div className="space-y-2.5">
                  {[
                    {
                      key: 'whitelist_auto',
                      title: 'Whitelist auto-accepts, others wait for you',
                      desc: 'Incoming transfers from approved creator handles are accepted automatically. Other transfers require manual approval.',
                    },
                    {
                      key: 'whitelist_only',
                      title: 'Whitelist only',
                      desc: 'Only accept transfers from users on your whitelist. All other requests are instantly declined.',
                    },
                    {
                      key: 'open',
                      title: 'Open',
                      desc: 'Accept all incoming transfers automatically without manual verification.',
                    },
                    {
                      key: 'disabled',
                      title: 'Disabled',
                      desc: 'Block all incoming transfers. Other users cannot send bots to your account.',
                    },
                  ].map((opt) => (
                    <label
                      key={opt.key}
                      onClick={() => handleSelectTransferConfig(opt.key as any)}
                      className={`p-3.5 rounded-2xl border transition-all flex items-start gap-3 cursor-pointer ${
                        settings.transferConfig === opt.key
                          ? 'bg-blue-50/70 dark:bg-blue-950/40 border-blue-500 dark:border-blue-500 shadow-xs'
                          : 'bg-white dark:bg-slate-800/60 border-slate-200 dark:border-slate-700/60 hover:border-slate-300 dark:hover:border-slate-600'
                      }`}
                    >
                      <input
                        type="radio"
                        name="transferConfig"
                        checked={settings.transferConfig === opt.key}
                        onChange={() => handleSelectTransferConfig(opt.key as any)}
                        className="mt-1 text-blue-600"
                      />
                      <div>
                        <span className="text-xs font-bold text-slate-900 dark:text-white block">
                          {opt.title}
                        </span>
                        <span className="text-xs text-slate-500 mt-0.5 block leading-relaxed">
                          {opt.desc}
                        </span>
                      </div>
                    </label>
                  ))}
                </div>

                {/* SENDER WHITELIST */}
                <div className="pt-4 border-t border-slate-200 dark:border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                      Sender whitelist · {settings.senderWhitelist.length}/100
                    </label>
                    <span className="text-[11px] text-slate-400">
                      Approved email senders & Telegram handles
                    </span>
                  </div>

                  <form onSubmit={handleAddWhitelist} className="flex gap-2">
                    <input
                      type="text"
                      value={newWhitelistEmail}
                      onChange={(e) => setNewWhitelistEmail(e.target.value)}
                      placeholder="trusted@example.com"
                      className="flex-1 px-3.5 py-2.5 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                    />
                    <button
                      type="submit"
                      className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold cursor-pointer transition-colors shadow-xs shrink-0 flex items-center gap-1.5"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add
                    </button>
                  </form>

                  {/* Whitelist Chips with Remove (×) button */}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {settings.senderWhitelist.map((item) => (
                      <span
                        key={item}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-mono font-medium bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200"
                      >
                        {item}
                        <button
                          type="button"
                          onClick={() => handleRemoveWhitelist(item)}
                          title={`Remove ${item}`}
                          className="text-slate-400 hover:text-rose-500 cursor-pointer transition-colors ml-1 p-0.5 rounded-full"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>

                {/* OUTGOING LIMIT */}
                <div className="pt-4 border-t border-slate-200 dark:border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                        Outgoing limit
                      </h4>
                      <p className="text-xs text-slate-500">Bots per 10 minutes</p>
                    </div>
                    <div className="px-3 py-1 rounded-xl bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 font-mono font-black text-sm">
                      {outgoingLimitInput} / 50
                    </div>
                  </div>

                  {/* Range Slider / Volume Progress Bar */}
                  <div className="space-y-2">
                    <input
                      type="range"
                      min={1}
                      max={50}
                      value={outgoingLimitInput}
                      onChange={(e) => setOutgoingLimitInput(Number(e.target.value))}
                      className="w-full h-2.5 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    />
                    <div className="flex justify-between text-[10px] font-mono text-slate-400">
                      <span>1 bot</span>
                      <span>25 bots</span>
                      <span>50 bots (Maximum)</span>
                    </div>
                  </div>

                  {/* Slide to save outgoing limit (replaces the save button) */}
                  <div className="space-y-2 pt-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                        <Sliders className="w-3.5 h-3.5 text-blue-500" />
                        <span>Confirm Outgoing Limit ({outgoingLimitInput} bots / 10m)</span>
                      </span>
                      <span className="text-[11px] text-slate-400">
                        Slide fully to save
                      </span>
                    </div>

                    <div
                      ref={limitSliderRef}
                      className="relative w-full h-14 rounded-2xl bg-slate-100 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 overflow-hidden select-none p-1 flex items-center shadow-inner"
                    >
                      {/* Fill track */}
                      <div
                        className="absolute left-0 top-0 bottom-0 bg-gradient-to-r from-blue-600/30 to-emerald-600/40 transition-all"
                        style={{ width: `${limitSliderVal}%` }}
                      />

                      {/* Center guide text - positioned to never collide with knob */}
                      <div
                        className="absolute inset-y-0 left-14 right-3 flex items-center justify-center pointer-events-none text-[11px] sm:text-xs font-bold text-slate-500 dark:text-slate-400 tracking-tight sm:tracking-wide text-center truncate transition-opacity"
                        style={{ opacity: Math.max(0, 1 - limitSliderVal / 45) }}
                      >
                        {limitSliderVal >= 90
                          ? 'Release to save limit!'
                          : 'Slide to save outgoing limit →'}
                      </div>

                      {/* Slider draggable knob */}
                      <div
                        onMouseDown={() => setIsSlidingLimit(true)}
                        onTouchStart={() => setIsSlidingLimit(true)}
                        style={{
                          transform: `translateX(${(limitSliderVal / 100) * ((limitSliderRef.current?.offsetWidth || 300) - 56)}px)`,
                        }}
                        className="relative z-10 w-12 h-12 rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 text-white dark:text-slate-900 flex items-center justify-center cursor-grab active:cursor-grabbing shadow-md transition-transform duration-75"
                        title="Slide to save outgoing limit"
                      >
                        <Check className="w-5 h-5 text-emerald-400 dark:text-emerald-600" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* TAB 4: SECURITY */}
          {activeSubTab === 'security' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <Shield className="w-5 h-5 text-emerald-500" />
                    Security
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Fine-tune runtime execution permissions and device sessions.
                  </p>
                </div>

                <SecurityCenterCard />

                {/* BOT CODE PERMISSIONS */}
                <div className="space-y-2 pb-4 border-b border-slate-200 dark:border-slate-800">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Bot code permissions
                  </h4>

                  <div className="flex items-start justify-between gap-4 p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-900 dark:text-white">
                          Allow bot code to delete bots
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 font-mono text-slate-700 dark:text-slate-300">
                          Account.delete_bot
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 leading-relaxed">
                        Lets <code className="font-mono text-blue-600 dark:text-blue-400">Account.delete_bot</code> run inside your commands.
                      </p>
                      <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                        Off by default. Your bots&apos; own code cannot delete bots unless you turn this on — and a bot transferred to you can never delete bots for its first 48 hours.
                      </p>
                    </div>

                    {/* On/Off Switch */}
                    <button
                      type="button"
                      onClick={handleToggleDeletePermission}
                      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                        settings.allowBotCodeToDeleteBots
                          ? 'bg-emerald-600'
                          : 'bg-slate-300 dark:bg-slate-700'
                      }`}
                    >
                      <span
                        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                          settings.allowBotCodeToDeleteBots ? 'translate-x-5' : 'translate-x-0'
                        }`}
                      />
                    </button>
                  </div>
                </div>

                {/* SESSIONS */}
                <div className="space-y-3 pb-4 border-b border-slate-200 dark:border-slate-800">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                        Sessions
                      </h4>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Signs out every browser and device, including this one. We email a code first, so a stolen session cannot use this.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleSignOutAllOtherSessions}
                      className="px-3.5 py-2 rounded-xl border border-rose-200 dark:border-rose-900/60 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-xs font-bold transition-colors cursor-pointer shrink-0 self-start sm:self-auto flex items-center gap-1.5"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                      Terminate All Other Sessions
                    </button>
                  </div>

                  {/* Device list */}
                  <div className="space-y-2 pt-2">
                    {settings.activeSessions.length === 0 ? (
                      <p className="text-xs text-slate-500 text-center py-6">No other sessions — only this device is signed in.</p>
                    ) : settings.activeSessions.map((sess) => (
                      <div
                        key={sess.id}
                        className="p-3.5 rounded-2xl bg-white dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/60 flex items-center justify-between gap-3 text-xs"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-300 shrink-0">
                            {sess.clientType === 'mobile' ? (
                              <Smartphone className="w-4 h-4" />
                            ) : (
                              <Laptop className="w-4 h-4" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-slate-900 dark:text-white truncate">
                                {sess.device}
                              </span>
                              {sess.isCurrent && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 font-bold shrink-0">
                                  This device
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-500 font-mono truncate">
                              {sess.ip} • {sess.location} • {sess.lastActive}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-3 shrink-0">
                          <span
                            className={`inline-flex items-center gap-1 text-[11px] font-bold ${
                              sess.status === 'online'
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-slate-400'
                            }`}
                          >
                            <span
                              className={`w-2 h-2 rounded-full ${
                                sess.status === 'online' ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400'
                              }`}
                            />
                            {sess.status === 'online' ? 'Online' : 'Offline'}
                          </span>

                          {!sess.isCurrent && (
                            <button
                              type="button"
                              onClick={() => handleRevokeSession(sess.id)}
                              className="text-xs text-rose-500 hover:text-rose-600 font-semibold cursor-pointer"
                            >
                              Revoke
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* TAB 5: PLAN */}
          {activeSubTab === 'plan' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-slate-200/80 dark:border-slate-800/80 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <CreditCard className="w-5 h-5 text-purple-500" />
                    Plan &amp; Quota
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Your current subscription allocation and point allowance.
                  </p>
                </div>

                {/* Plan Details Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                      Plan
                    </span>
                    <span className="text-lg font-black text-slate-900 dark:text-white mt-1 block">
                      {settings.plan.name}
                    </span>
                  </div>

                  <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 min-w-0 overflow-hidden">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                      Remaining points
                    </span>
                    <span title={(settings?.plan?.remainingPoints ?? 0).toLocaleString()} className="text-base sm:text-lg font-black text-blue-600 dark:text-blue-400 font-mono mt-1 block truncate">
                      {fmtPts(settings?.plan?.remainingPoints ?? 0)}
                    </span>
                  </div>

                  <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                      Extra points
                    </span>
                    <span title={Number(settings.plan.extraPoints || 0).toLocaleString()} className="text-base sm:text-lg font-black text-slate-900 dark:text-white font-mono mt-1 block truncate">
                      {fmtPts(Number(settings.plan.extraPoints || 0))}
                    </span>
                  </div>

                  <div className="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
                    <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block">
                      Resets on
                    </span>
                    <span className="text-lg font-black text-slate-900 dark:text-white font-mono mt-1 block">
                      {settings.plan.resetsOn}
                    </span>
                  </div>
                </div>

                {/* Action Buttons: Change Plan & Billing Support */}
                <div className="flex flex-wrap gap-3 pt-2">
                  <a
                    href={settings.plan.changePlanTg || undefined}
                    target="_blank"
                    rel="noreferrer"
                    className="px-5 py-2.5 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs shadow-md shadow-blue-500/20 transition-all cursor-pointer flex items-center gap-2"
                  >
                    <Send className="w-4 h-4" />
                    Change plan
                  </a>

                  <a
                    href={settings.plan.billingSupportTg || undefined}
                    target="_blank"
                    rel="noreferrer"
                    className="px-5 py-2.5 rounded-2xl bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 font-bold text-xs transition-colors cursor-pointer flex items-center gap-2"
                  >
                    <ExternalLink className="w-4 h-4" />
                    Billing support
                  </a>
                </div>
              </div>
            </motion.div>
          )}

          {/* TAB 6: DANGER ZONE */}
          {activeSubTab === 'danger' && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-6"
            >
              <div className="glass-panel p-6 sm:p-7 rounded-3xl border border-rose-300 dark:border-rose-900/60 bg-rose-50/20 dark:bg-rose-950/10 space-y-6">
                <div>
                  <h3 className="text-base font-bold text-rose-600 dark:text-rose-400 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    Danger Zone
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Irreversible account operations and complete workspace purge.
                  </p>
                </div>

                <div className="p-5 rounded-2xl bg-white dark:bg-slate-900/80 border border-rose-200 dark:border-rose-900/50 space-y-4">
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                      Delete account
                    </h4>
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                      Stops and removes every bot. 3-day grace period — log in again to cancel.
                    </p>
                  </div>

                  {/* Confirmation input box */}
                  <div className="space-y-1.5 max-w-md">
                    <label className="block text-xs font-bold text-slate-700 dark:text-slate-300">
                      Confirmation string
                    </label>
                    <input
                      type="text"
                      value={deleteConfirmText}
                      onChange={(e) => setDeleteConfirmText(e.target.value)}
                      placeholder="Type DELETE to confirm"
                      className="w-full px-3.5 py-2.5 rounded-xl text-xs bg-slate-50 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-rose-500/30"
                    />
                  </div>

                  {/* Slider to Delete My Account */}
                  <div className="space-y-2 max-w-md pt-1">
                    <div className="flex items-center justify-between text-xs">
                      <span
                        className={`font-bold ${
                          deleteConfirmText === 'DELETE'
                            ? 'text-rose-600 dark:text-rose-400'
                            : 'text-slate-400'
                        }`}
                      >
                        Delete my account
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {deleteConfirmText === 'DELETE'
                          ? 'Slide fully to finalize'
                          : 'Type DELETE first'}
                      </span>
                    </div>

                    <div
                      ref={deleteSliderRef}
                      className={`relative w-full h-14 rounded-2xl border overflow-hidden select-none p-1 flex items-center transition-opacity ${
                        deleteConfirmText === 'DELETE'
                          ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-300 dark:border-rose-800 opacity-100'
                          : 'bg-slate-100 dark:bg-slate-900 border-slate-200 dark:border-slate-800 opacity-50 cursor-not-allowed'
                      }`}
                    >
                      <div
                        className="absolute left-0 top-0 bottom-0 bg-gradient-to-r from-rose-500 to-rose-700 transition-all"
                        style={{ width: `${deleteSliderVal}%` }}
                      />

                      {/* Guide text - positioned safely after knob */}
                      <div
                        className="absolute inset-y-0 left-14 right-3 flex items-center justify-center pointer-events-none text-[11px] sm:text-xs font-bold text-slate-500 dark:text-slate-400 tracking-tight sm:tracking-wide text-center truncate transition-opacity"
                        style={{ opacity: Math.max(0, 1 - deleteSliderVal / 45) }}
                      >
                        {deleteSliderVal >= 90
                          ? 'Release to delete account!'
                          : 'Slide to delete account →'}
                      </div>

                      <div
                        onMouseDown={() => {
                          if (deleteConfirmText === 'DELETE') setIsSlidingDelete(true);
                        }}
                        onTouchStart={() => {
                          if (deleteConfirmText === 'DELETE') setIsSlidingDelete(true);
                        }}
                        style={{
                          transform: `translateX(${(deleteSliderVal / 100) * ((deleteSliderRef.current?.offsetWidth || 300) - 56)}px)`,
                        }}
                        className={`relative z-10 w-12 h-12 rounded-xl text-white flex items-center justify-center shadow-md transition-transform duration-75 ${
                          deleteConfirmText === 'DELETE'
                            ? 'bg-rose-600 hover:bg-rose-700 cursor-grab active:cursor-grabbing shadow-rose-500/30'
                            : 'bg-slate-400 dark:bg-slate-700 cursor-not-allowed'
                        }`}
                      >
                        <Trash2 className="w-5 h-5" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Disconnect Telegram Confirmation Dialog */}
      <ConfirmationModal
        isOpen={showDisconnectConfirm}
        onClose={() => setShowDisconnectConfirm(false)}
        onConfirm={handleDisconnectTelegram}
        title="Disconnect Telegram"
        message="Are you sure you want to disconnect your Telegram account? Push alerts for bot events, restarts, and transfers will be paused until reconnected."
        confirmText="Yes, Disconnect"
        cancelText="Cancel"
        isDestructive={true}
      />
    </div>
  );
};
