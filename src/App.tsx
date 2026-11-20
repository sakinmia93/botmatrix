import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { AuthModal } from './components/AuthModal';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { DashboardView } from './components/DashboardView';
import { MyBotsView } from './components/MyBotsView';
import { BotStudioView } from './components/BotStudioView';
import { BroadcastView } from './components/BroadcastView';
import { BotStoreView } from './components/BotStoreView';
import { PricingBillingView } from './components/PricingBillingView';
import { AdminView } from './components/AdminView';
import {
  RecycleBinView,
  TransfersView,
  SettingsView,
  HelpSupportView,
} from './components/OtherViews';
// Real data only — loaded from backend API (no mock seeds)
import { User, PageTab, BotItem, BotStatus, BroadcastItem, StoreBot } from './types';
import { CheckCircle2, Sparkles, RefreshCw } from 'lucide-react';
import {
  DashboardSkeleton,
  BotGridSkeleton,
  BotStoreSkeleton,
  TableListSkeleton,
  GenericPageSkeleton,
} from './components/SkeletonScreen';
import { apiService, clearAuthToken, getAuthToken, apiErrorMessage } from './services/apiService';
import { getPlatformSettings, loadPlatformSettings } from './data/platformStore';
import { safeGet, safeJsonParse, safeRemove } from './utils/safeStorage';

export default function App() {
  // Theme state: defaults to false (clean white grid mode as requested), supports dark mode
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    try {
      return safeGet('telebot_theme') === 'dark';
    } catch {
      return false;
    }
  });

  // User auth state: only restore if a session token still exists (respects Remember me)
  const [user, setUser] = useState<User | null>(() => {
    if (typeof window === 'undefined') return null;
    try {
      const token = getAuthToken();
      if (!token) {
        safeRemove('telebot_user');
        return null;
      }
      const saved = safeGet('telebot_user');
      const parsed = safeJsonParse<any>(saved, null);
      if (!parsed || typeof parsed !== 'object') {
        safeRemove('telebot_user');
        return null;
      }
      return parsed as User;
    } catch {
      try { safeRemove('telebot_user'); } catch {}
      return null;
    }
  });

  // Active navigation tab
  const [activeTab, setActiveTab] = useState<PageTab>(() => {
    if (typeof window === 'undefined') return 'Dashboard';
    try {
      const saved = safeGet('telebot_active_tab') as PageTab | null;
      const allowed: PageTab[] = [
        'Dashboard', 'My Bots', 'Bot Store', 'Plans & Billing', 'Broadcast Manager',
        'Recycle Bin', 'Transfers', 'Settings', 'Notifications', 'Help', 'Support', 'Admin',
      ];
      if (saved && (allowed as string[]).includes(saved)) return saved;
    } catch {}
    return 'Dashboard';
  });

  // Selected bot ID for Bot Studio editor view
  const [selectedBotId, setSelectedBotId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    try {
      return safeGet('telebot_selected_bot') || null;
    } catch {
      return null;
    }
  });

  // Mobile/desktop sidebar drawer toggle state
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // Bot clusters and telemetry state
  const [bots, setBots] = useState<BotItem[]>([]);
  const selectedBot = bots.find((b) => b.id === selectedBotId);
  const [recycleBots, setRecycleBots] = useState<BotItem[]>([]);
  const [activityData, setActivityData] = useState<{ time: string; users: number; commands: number }[]>([]);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [notifsLoaded, setNotifsLoaded] = useState(false);

  // Browser push permission after login
  useEffect(() => {
    if (typeof window === 'undefined' || !('Notification' in window) || !user) return;
    if (Notification.permission === 'default') {
      const key = 'bmp_notif_asked';
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1');
        Notification.requestPermission().catch(() => {});
      }
    }
  }, [user]);

  const [prefsReady, setPrefsReady] = useState(false);
  useEffect(() => {
    if (!user) { setPrefsReady(false); return; }
    loadPlatformSettings().catch(() => {}).finally(() => setPrefsReady(true));
  }, [user?.id]);

  // Browser pop-ups: each notification is shown only once, ever (remembered across reloads)
  useEffect(() => {
    if (typeof window === 'undefined' || !user || !notifsLoaded || !prefsReady) return;
    const ps = getPlatformSettings();
    const popupsOn = ps.notificationsEnabled !== false && ps.browserPopups !== false;
    const KEY = `bm_notif_shown_${user.id}`;
    let shown: string[] | null = null;
    try { const raw = localStorage.getItem(KEY); shown = raw ? JSON.parse(raw) : null; } catch { shown = null; }
    const ids = (notifications || []).map((n: any) => String(n.id));
    if (shown === null) {
      // First run: only mark *already-read* items as seen so unread ones can still
      // trigger a browser/OS notification (the "signal" the user expects).
      const seed = (notifications || []).filter((n: any) => n.read).map((n: any) => String(n.id));
      try { localStorage.setItem(KEY, JSON.stringify(seed.slice(0, 500))); } catch {}
      shown = seed;
    }
    const fresh = (notifications || []).filter((n: any) => !n.read && !shown!.includes(String(n.id)));
    if (!fresh.length) return;
    try { localStorage.setItem(KEY, JSON.stringify([...fresh.map((n: any) => String(n.id)), ...shown].slice(0, 500))); } catch {}
    if (!popupsOn || !('Notification' in window)) return;
    if (Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {});
      return;
    }
    if (Notification.permission !== 'granted') return;
    fresh.slice(0, 5).forEach((n: any) => {
      try {
        const pn = new Notification(n.title || 'BOT MATRIX', { body: n.message || '', icon: '/logo.jpg', tag: `bm-${n.id}` });
        pn.onclick = () => { try { window.focus(); } catch (_) {} openNotifRef.current?.(n); pn.close(); };
      } catch (_) {}
    });
  }, [notifications, user, notifsLoaded, prefsReady]);
  const openNotifRef = useRef<((n: any) => void) | null>(null);
  const [broadcasts, setBroadcasts] = useState<BroadcastItem[]>([]);

  // Search query
  const [searchQuery, setSearchQuery] = useState('');

  // Real-time refresh state
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastUpdatedTime, setLastUpdatedTime] = useState('Just now');
  const [refreshToast, setRefreshToast] = useState<string | null>(null);
  const flash = (msg: string, ms = 3500) => {
    setRefreshToast(msg);
    setTimeout(() => setRefreshToast(null), ms);
  };

  // Tab transition loading skeleton state
  const [isLoadingTab, setIsLoadingTab] = useState(false);

  // Animation settings state (respects "Disable Animations" setting)
  const [disableAnimations, setDisableAnimations] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('telebot_disable_animations') === 'true';
    }
    return false;
  });

  // Listen for dynamic animation settings changes
  useEffect(() => {
    const handleAnimChange = (e: any) => {
      if (e.detail !== undefined) {
        setDisableAnimations(Boolean(e.detail));
      }
    };
    const handleSettingsUpdate = (e: any) => {
      if (e.detail && e.detail.disableAnimations !== undefined) {
        setDisableAnimations(Boolean(e.detail.disableAnimations));
      }
    };
    window.addEventListener('telebot_animation_setting_changed', handleAnimChange);
    window.addEventListener('telebot_settings_updated', handleSettingsUpdate);
    return () => {
      window.removeEventListener('telebot_animation_setting_changed', handleAnimChange);
      window.removeEventListener('telebot_settings_updated', handleSettingsUpdate);
    };
  }, []);


  // Persist navigation so refresh stays on same page
  useEffect(() => {
    localStorage.setItem('telebot_active_tab', activeTab);
  }, [activeTab]);
  useEffect(() => {
    if (selectedBotId) localStorage.setItem('telebot_selected_bot', selectedBotId);
    else localStorage.removeItem('telebot_selected_bot');
  }, [selectedBotId]);

  // Force logout handler for session revocation / security enforcement
  useEffect(() => {
    const handleForceLogout = () => {
      setUser(null);
      try { clearAuthToken(); } catch {} /* token cleared */
      localStorage.removeItem('telebot_user');
      setRefreshToast('Session terminated or invalidated. Please sign in again.');
      setTimeout(() => setRefreshToast(null), 4000);
    };

    const handlePointsDepleted = () => {
      setBots((prev) => prev.map((b) => ({ ...b, status: 'stopped' as BotStatus, uptime: '00:00:00' })));
      setRefreshToast('Points balance exhausted (0 pts). All bots halted automatically.');
      setTimeout(() => setRefreshToast(null), 5000);
    };

    window.addEventListener('telebot_force_logout', handleForceLogout);
    window.addEventListener('telebot_points_depleted', handlePointsDepleted);
    return () => {
      window.removeEventListener('telebot_force_logout', handleForceLogout);
      window.removeEventListener('telebot_points_depleted', handlePointsDepleted);
    };
  }, []);

  // Verify active session with Python backend on app mount
  useEffect(() => {
    if (user) {
      apiService.getMe().then((res) => {
        if (!res || !res.user) {
          // Session deleted or revoked in backend
          setUser(null);
          try { clearAuthToken(); } catch {} /* token cleared */
          localStorage.removeItem('telebot_user');
        } else {
          setUser(res.user);
        }
      }).catch(() => {});
    }
  }, []);

  // Fetch ALL real data from backend when user is authenticated (empty arrays if none)
  useEffect(() => {
    if (!user) {
      setBots([]);
      setNotifications([]);
      setBroadcasts([]);
      setRecycleBots([]);
      setActivityData([]);
      return;
    }

    let cancelled = false;

    const loadAll = async () => {
      try {
        const [backendBots, notifs, bcs, rb] = await Promise.all([
          apiService.getBots().catch(() => [] as BotItem[]),
          apiService.getNotifications().catch(() => [] as any[]),
          apiService.getBroadcasts().catch(() => [] as BroadcastItem[]),
          apiService.getRecycleBin().catch(() => [] as any[]),
        ]);
        if (cancelled) return;
        setBots(Array.isArray(backendBots) ? backendBots : []);
        setNotifications(Array.isArray(notifs) ? notifs : []);
        setNotifsLoaded(true);
        setBroadcasts(Array.isArray(bcs) ? bcs : []);
        setRecycleBots(Array.isArray(rb) ? rb : []);
        apiService.getDashboardStats().then((st) => {
          if (!cancelled && st && Array.isArray(st.activity)) setActivityData(st.activity);
        }).catch(() => {});
      } catch {
        if (!cancelled) {
          setBots([]);
          setNotifications([]);
          setBroadcasts([]);
          setRecycleBots([]);
        }
      }
    };

    loadAll();
    return () => { cancelled = true; };
  }, [user]);

  // Keep data live: broadcasts every 1.5s while one is running, bots / notifications every 12s
  useEffect(() => {
    if (!user) return;
    const running = broadcasts.some((b) => b.status === 'Active' || b.status === 'Paused');
    if (!running) return;
    const t = setInterval(() => {
      apiService.getBroadcasts().then((list) => {
        if (Array.isArray(list)) setBroadcasts(list);
      }).catch(() => {});
    }, 1500);
    return () => clearInterval(t);
  }, [user, broadcasts.some((b) => b.status === 'Active' || b.status === 'Paused')]);

  // notifications: checked every 4 seconds, and right away when the tab comes back into view
  useEffect(() => {
    if (!user) return;
    const pull = () => apiService.getNotifications().then((list) => { if (Array.isArray(list)) { setNotifications(list); setNotifsLoaded(true); } }).catch(() => {});
    const t = setInterval(pull, 4000);
    const onVis = () => { if (!document.hidden) pull(); };
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('focus', pull);
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVis); window.removeEventListener('focus', pull); };
  }, [user?.id]);

  useEffect(() => {
    if (!user) return;
    const t = setInterval(() => {
      if (document.hidden) return;
      apiService.getBots().then((list) => { if (Array.isArray(list)) setBots(list); }).catch(() => {});
      apiService.getNotifications().then((list) => { if (Array.isArray(list)) setNotifications(list); }).catch(() => {});
      apiService.getDashboardStats().then((st) => { if (st && Array.isArray(st.activity)) setActivityData(st.activity); }).catch(() => {});
    }, 12000);
    return () => clearInterval(t);
  }, [user]);

  // Smooth tab switching with simulated skeleton loading for heavy views
  const handleTabChange = (nextTab: PageTab) => {
    if (nextTab === activeTab && !selectedBotId) return;
    setIsLoadingTab(true);
    setActiveTab(nextTab);
    if (nextTab !== 'My Bots') {
      setSelectedBotId(null);
    }
    setTimeout(() => {
      setIsLoadingTab(false);
    }, 380);
  };

  // Sync dark mode class with html root element
  useEffect(() => {
    const root = document.documentElement;
    if (isDarkMode) {
      root.classList.add('dark');
      localStorage.setItem('telebot_theme', 'dark');
    } else {
      root.classList.remove('dark');
      localStorage.setItem('telebot_theme', 'light');
    }
  }, [isDarkMode]);

  // Persist user session
  const handleAuthSuccess = (authenticatedUser: User) => {
    setUser(authenticatedUser);
    localStorage.setItem('telebot_user', JSON.stringify(authenticatedUser));
    setActiveTab('Dashboard');
  };

  const handleLogout = () => {
    apiService.logout().catch(() => {});
    setUser(null);
    localStorage.removeItem('telebot_user');
    try { clearAuthToken(); } catch {} /* token cleared */
  };

  const handleToggleTheme = () => {
    setIsDarkMode((prev) => !prev);
  };

  // Real-time data refresh handler
  useEffect(() => {
    const h = () => { handleRefreshData(); };
    window.addEventListener('bm_refresh', h);
    return () => window.removeEventListener('bm_refresh', h);
  });

  const handleRefreshData = () => {
    if (isRefreshing) return;
    setIsRefreshing(true);

    Promise.all([
      apiService.getBots().catch(() => null),
      apiService.getNotifications().catch(() => null),
      apiService.getBroadcasts().catch(() => null),
      apiService.getRecycleBin().catch(() => null),
    ]).then(([backendBots, notifs, bcs, rb]) => {
      if (Array.isArray(backendBots)) setBots(backendBots);
      if (Array.isArray(notifs)) { setNotifications(notifs); setNotifsLoaded(true); }
      if (Array.isArray(bcs)) setBroadcasts(bcs);
      if (Array.isArray(rb)) setRecycleBots(rb);
    });

    setTimeout(() => {

      const now = new Date();
      const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      setLastUpdatedTime(timeStr);
      setIsRefreshing(false);

      setRefreshToast('Data refreshed');
      setTimeout(() => setRefreshToast(null), 3500);
    }, 600);
  };

  // Bot management actions with backend persistence
  const handleToggleBotStatus = async (botId: string) => {
    try {
      const updated = await apiService.toggleBotStatus(botId);
      setBots((prev) => prev.map((b) => (b.id === botId ? { ...b, ...updated } : b)));
    } catch (err: any) {
      flash(apiErrorMessage(err, 'Could not change the bot status.'), 4500);
      apiService.getBots().then((list) => { if (Array.isArray(list)) setBots(list); }).catch(() => {});
    }
  };

  const handleMoveToRecycleBin = (botId: string) => {
    const botToMove = bots.find((b) => b.id === botId);
    if (!botToMove) return;

    const nowIso = new Date().toISOString();
    apiService.deleteBot(botId).then(() => {
      setBots((prev) => prev.filter((b) => b.id !== botId));
      setRecycleBots((prev) => [{ ...botToMove, chats: undefined, inRecycleBin: true, status: 'stopped', deletedAt: nowIso }, ...prev]);
      if (selectedBotId === botId) {
        setSelectedBotId(null);
      }
      flash(`Moved ${botToMove.name} to Recycle Bin (10-Day Retention Hold started)`);
    }).catch((err) => flash(apiErrorMessage(err, 'Could not delete the bot.'), 4500));
  };

  const handleRestoreBot = (botId: string) => {
    const botToRestore = recycleBots.find((b) => b.id === botId);
    if (!botToRestore) return;

    apiService.restoreBotFromRecycleBin(botId).then((res: any) => {
      const restored = res?.bot || { ...botToRestore, inRecycleBin: false, status: 'stopped' as BotStatus };
      setRecycleBots((prev) => prev.filter((b) => b.id !== botId));
      setBots((prev) => [restored, ...prev.filter((b) => b.id !== restored.id)]);
      flash(`Restored ${botToRestore.name} to active bots!`, 3000);
    }).catch((err) => flash(apiErrorMessage(err, 'Could not restore the bot.'), 4500));
  };

  const handlePermanentlyDelete = (botId: string) => {
    const targetBot = recycleBots.find((b) => b.id === botId);
    const deletedTime = targetBot?.deletedAt ? new Date(targetBot.deletedAt).getTime() : Date.now();
    const daysPassed = (Date.now() - deletedTime) / (1000 * 60 * 60 * 24);

    if (daysPassed < 10) {
      const daysRemaining = Math.max(1, Math.ceil(10 - daysPassed));
      setRefreshToast(`Cannot delete permanently: 10-day safety retention hold active (${daysRemaining} day(s) remaining).`);
      setTimeout(() => setRefreshToast(null), 4000);
      return;
    }

    apiService.permanentlyDeleteBot(botId).then((res) => {
      if (res && res.error) {
        setRefreshToast(res.error);
        setTimeout(() => setRefreshToast(null), 4000);
      } else {
        setRecycleBots((prev) => prev.filter((b) => b.id !== botId));
        setRefreshToast(`Permanently purged bot from database.`);
        setTimeout(() => setRefreshToast(null), 3000);
      }
    }).catch((err) => flash(apiErrorMessage(err, 'Could not delete the bot.'), 4500));
  };

  const handleEmptyRecycleBin = () => {
    // Only bots that passed 10-day retention can be deleted
    const eligibleToDelete = recycleBots.filter((b) => {
      const delTime = b.deletedAt ? new Date(b.deletedAt).getTime() : Date.now();
      return (Date.now() - delTime) / (1000 * 60 * 60 * 24) >= 10;
    });

    if (eligibleToDelete.length === 0) {
      setRefreshToast('No bots are eligible for permanent deletion yet. All items are under the mandatory 10-day retention safety hold.');
      setTimeout(() => setRefreshToast(null), 4500);
      return;
    }

    Promise.all(eligibleToDelete.map((b) => apiService.permanentlyDeleteBot(b.id).then(() => b.id).catch(() => null))).then((ids) => {
      const done = ids.filter(Boolean) as string[];
      setRecycleBots((prev) => prev.filter((b) => !done.includes(b.id)));
      flash(`Permanently deleted ${done.length} eligible bot(s). Items under 10-day hold remain protected.`, 4000);
    });
  };

  const handleCreateBot = async (newBotData: Partial<BotItem>) => {
    try {
      const created = await apiService.createBot({
        token: newBotData.token,
        name: newBotData.name,
        username: newBotData.username,
        folder: newBotData.folder || '',
        category: newBotData.category || 'General',
        commands: newBotData.commands || [],
        envVars: newBotData.envVars || [],
      });
      setBots((prev) => [created, ...prev.filter((b) => b.id !== created.id)]);
      setRefreshToast(`Connected ${created.name || created.username} successfully`);
      setTimeout(() => setRefreshToast(null), 3500);
      return created;
    } catch (err: any) {
      // Pull fresh list — create may have succeeded server-side before a timeout
      try {
        const list = await apiService.getBots();
        if (Array.isArray(list)) setBots(list);
      } catch {}
      throw err;
    }
  };

  const handleUpdateBot = (updatedBot: BotItem) => {
    // show the change immediately, then let the server confirm (or roll back with the real message)
    setBots((prev) => prev.map((b) => (b.id === updatedBot.id ? updatedBot : b)));
    return apiService.updateBot(updatedBot).then((saved) => {
      setBots((prev) => prev.map((b) => (b.id === saved.id ? { ...b, ...saved } : b)));
      return saved;
    }).catch((err) => {
      flash(apiErrorMessage(err, 'Could not save your changes.'), 5000);
      apiService.getBots().then((list) => { if (Array.isArray(list)) setBots(list); }).catch(() => {});
      throw err;
    });
  };

  const handleCloneBot = async (originalBot: BotItem) => {
    // Rate limit: max 2 clones of same bot per 5 minutes
    const key = `clone_rate_${originalBot.id}`;
    try {
      const raw = localStorage.getItem(key);
      const stamps: number[] = raw ? JSON.parse(raw) : [];
      const now = Date.now();
      const recent = stamps.filter((t) => now - t < 5 * 60 * 1000);
      if (recent.length >= 2) {
        setRefreshToast('Clone limit: max 2 clones per bot every 5 minutes');
        setTimeout(() => setRefreshToast(null), 4000);
        return;
      }
      recent.push(now);
      localStorage.setItem(key, JSON.stringify(recent));
    } catch {}

    try {
      // Clone without token — backend creates new id; user must add token later
      const cloned = await apiService.createBot({
        name: `${originalBot.name} (Clone)`,
        username: originalBot.username,
        folder: originalBot.folder || '',
        category: originalBot.category || 'General',
        commands: originalBot.commands || [],
        envVars: originalBot.envVars || [],
        token: '',
        isClone: true,
        description: originalBot.description,
      } as any);
      setBots((prev) => [cloned, ...prev]);
      flash(`Cloned ${originalBot.name}`);
    } catch (err) {
      flash(apiErrorMessage(err, 'Clone failed.'), 4500);
    }
  };

  const handleMarkNotificationAsRead = (id: string) => {
    apiService.markNotificationRead(id).catch(() => {});
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  };

  // Clicking a notification opens the exact place it came from
  const handleOpenNotification = (n: any) => {
    handleMarkNotificationAsRead(n.id);
    const text = `${n.title} ${n.message}`.toLowerCase();
    let link: string = n.link || '';
    if (!link) {
      link = /transfer/.test(text) ? 'tab:Transfers' : /broadcast/.test(text) ? 'tab:Broadcast Manager'
        : /points|plan/.test(text) ? 'tab:Plans & Billing' : '';
    }
    if (link.startsWith('bot:')) {
      const id = link.slice(4);
      setActiveTab('My Bots');
      setSelectedBotId(bots.some((b) => b.id === id) ? id : null);
    } else if (link.startsWith('tab:')) {
      const [tabName, sub] = link.slice(4).split('#');
      if (tabName === 'Settings' && sub) {
        try { localStorage.setItem('telebot_settings_active_subtab', sub); } catch {}
        window.dispatchEvent(new CustomEvent('bm_settings_tab', { detail: sub }));
      }
      if (tabName === activeTab && !selectedBotId) { /* already there */ }
      else handleTabChange(tabName as PageTab);
    }
    setIsSidebarOpen(false);
  };

  openNotifRef.current = handleOpenNotification;

  const handleDeployStoreBot = async (storeBot: StoreBot) => {
    try {
      const res = await apiService.cloneStoreBot(storeBot.id);
      if (res?.bot) setBots((prev) => [res.bot, ...prev.filter((b) => b.id !== res.bot.id)]);
      flash(`Successfully cloned "${storeBot.name}"!`);
    } catch (err) {
      flash(apiErrorMessage(err, 'Could not clone this bot.'), 4500);
      throw err;
    }
  };

  // If user is not authenticated, render Login/Register Page with White Grid Background
  if (!user) {
    return (
      <AuthModal
        onSuccess={handleAuthSuccess}
        isDarkMode={isDarkMode}
        onToggleTheme={handleToggleTheme}
      />
    );
  }

  return (
    <div
      className={`min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors duration-300 ${
        isDarkMode ? 'dark' : ''
      }`}
    >
      {/* Toast Notification Alert */}
      <AnimatePresence>
        {refreshToast && (
          <motion.div
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            className="fixed top-4 right-4 z-50 px-4 py-2.5 rounded-2xl bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-2xl flex items-center gap-2.5 text-xs font-semibold border border-white/10 dark:border-slate-800"
          >
            <CheckCircle2 className="w-4 h-4 text-emerald-400 dark:text-emerald-600 shrink-0" />
            <span>{refreshToast}</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Responsive Sidebar (Mobile Drawer & Desktop Fixed) */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={handleTabChange}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        isDarkMode={isDarkMode}
        onToggleTheme={handleToggleTheme}
        onLogout={handleLogout}
        user={user}
        unreadCount={notifications.filter((n) => n && !n.read).length}
        botCount={bots.length}
        recycleCount={recycleBots.length}
      />

      {/* Main Content Area (Offset by lg:pl-72 on Desktop) */}
      <div className="lg:pl-72 flex-1 flex flex-col min-h-screen">
        {/* Top Header Navbar */}
        <Navbar
          activeTab={activeTab}
          subTitle={
            activeTab === 'My Bots' && selectedBot
              ? (() => {
                  const label = selectedBot.username || selectedBot.name || 'Bot';
                  const short = label.length > 24 ? `${label.slice(0, 24)}…` : label;
                  return `${short} · Studio`;
                })()
              : undefined
          }
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          onRefreshData={handleRefreshData}
          isRefreshing={isRefreshing}
          searchQuery={searchQuery}
          setSearchQuery={setSearchQuery}
          notifications={notifications}
          onMarkNotificationAsRead={handleMarkNotificationAsRead}
          onOpenNotification={handleOpenNotification}
          user={user}
          isDarkMode={isDarkMode}
          onToggleTheme={handleToggleTheme}
        />

        {/* Page Content View with Grid Background */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto bg-grid-pattern">
          <AnimatePresence mode="wait">
            <motion.div
              key={
                activeTab +
                (selectedBotId ? `-${selectedBotId}` : '') +
                (isLoadingTab || isRefreshing ? '-skeleton' : '')
              }
              initial={disableAnimations ? false : { opacity: 0, y: 14, scale: 0.995 }}
              animate={disableAnimations ? false : { opacity: 1, y: 0, scale: 1 }}
              exit={disableAnimations ? undefined : { opacity: 0, y: -10, scale: 0.995 }}
              transition={
                disableAnimations ? { duration: 0 } : { duration: 0.22, ease: [0.16, 1, 0.3, 1] }
              }
            >
              {isLoadingTab || isRefreshing ? (
                activeTab === 'Dashboard' ? (
                  <DashboardSkeleton />
                ) : activeTab === 'My Bots' && !selectedBotId ? (
                  <BotGridSkeleton />
                ) : activeTab === 'Bot Store' ? (
                  <BotStoreSkeleton />
                ) : activeTab === 'Transfers' ? (
                  <TableListSkeleton rows={5} />
                ) : activeTab === 'Recycle Bin' ? (
                  <TableListSkeleton rows={4} />
                ) : activeTab === 'Notifications' ? (
                  <TableListSkeleton rows={5} />
                ) : (
                  <GenericPageSkeleton />
                )
              ) : (
                <>
              {activeTab === 'Dashboard' && (
                <DashboardView
                  bots={bots}
                  activityData={activityData}
                  lastUpdatedTime={lastUpdatedTime}
                  onNavigateToBots={() => {
                    setSelectedBotId(null);
                    setActiveTab('My Bots');
                  }}
                  onCreateBotClick={() => {
                    setSelectedBotId(null);
                    setActiveTab('My Bots');
                  }}
                  onSelectBot={(bot) => {
                    setSelectedBotId(bot.id);
                    setActiveTab('My Bots');
                    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
                  }}
                />
              )}

              {activeTab === 'My Bots' && (
                selectedBot ? (
                  <BotStudioView
                    bot={selectedBot}
                    onBack={() => {
                      setSelectedBotId(null);
                      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
                    }}
                    onUpdateBot={handleUpdateBot}
                    onDeleteBot={(id) => {
                      handleMoveToRecycleBin(id);
                      setSelectedBotId(null);
                    }}
                    onCloneBot={handleCloneBot}
                    onOpenBroadcast={(id) => {
                      try { localStorage.setItem('bm_broadcast_open', id); localStorage.setItem('bm_broadcast_focus_bot', selectedBot.id); } catch {}
                      handleTabChange('Broadcast Manager');
                    }}
                  />
                ) : (
                  <MyBotsView
                    bots={bots}
                    onToggleStatus={handleToggleBotStatus}
                    onMoveToRecycleBin={handleMoveToRecycleBin}
                    onCreateBot={handleCreateBot}
                    searchQuery={searchQuery}
                    onOpenEditor={(bot) => {
                      setSelectedBotId(bot.id);
                      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
                    }}
                    onUpdateBot={handleUpdateBot}
                  />
                )
              )}

              {activeTab === 'Broadcast Manager' && (
                <BroadcastView
                  bots={bots}
                  broadcasts={broadcasts}
                  onSendBroadcast={(newBc) => {
                    // Already created by BroadcastView via API — only update local state once
                    setBroadcasts((prev) => [newBc, ...prev.filter((b) => b.id !== newBc.id)]);
                    flash(`Broadcast started: ${newBc.title || newBc.id}`, 3000);
                  }}
                  onDeleteBroadcast={(id) => {
                    apiService.deleteBroadcast(id).then(() => {
                      setBroadcasts((prev) => prev.filter((b) => b.id !== id));
                    }).catch((err) => flash(apiErrorMessage(err, 'Could not delete the broadcast.'), 4000));
                  }}
                  onUpdateBroadcast={(updatedBc) => {
                    setBroadcasts((prev) => prev.map((b) => b.id === updatedBc.id ? updatedBc : b));
                  }}
                  onRefreshBroadcasts={() => {
                    apiService.getBroadcasts().then((list) => { if (Array.isArray(list)) setBroadcasts(list); }).catch(() => {});
                  }}
                
                  onOpenBot={(botId, title) => {
                    try { sessionStorage.setItem('bm_highlight_bot', JSON.stringify({ id: botId, from: 'broadcast', title })); } catch {}
                    setActiveTab('My Bots');
                    setSelectedBotId(botId);
                    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
                  }}
                />
              )}

              {activeTab === 'Recycle Bin' && (
                <RecycleBinView
                  recycleBots={recycleBots}
                  onRestoreBot={handleRestoreBot}
                  onPermanentlyDelete={handlePermanentlyDelete}
                  onEmptyRecycleBin={handleEmptyRecycleBin}
                />
              )}

              {activeTab === 'Bot Store' && (
                <BotStoreView
                  onDeployStoreBot={handleDeployStoreBot}
                  onShowToast={(msg) => {
                    setRefreshToast(msg);
                    setTimeout(() => setRefreshToast(null), 3000);
                  }}
                  onNavigateToMyBots={() => {
                    setSelectedBotId(null);
                    setActiveTab('My Bots');
                  }}
                />
              )}

              {activeTab === 'Transfers' && <TransfersView />}

              {activeTab === 'Settings' && <SettingsView user={user} />}

              {activeTab === 'Notifications' && (
                <div className="space-y-6 pb-12 max-w-3xl">
                  <div className="flex items-center justify-between">
                    <div>
                      <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
                        All Notifications
                      </h1>
                      <p className="text-xs text-slate-500 mt-1">
                        Recent bot system events, webhooks, and alerts
                      </p>
                    </div>
                    <button
                      onClick={() => {
                        apiService.markAllNotificationsRead().catch(() => {});
                        setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
                      }}
                      className="px-3 py-1.5 rounded-xl bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400 text-xs font-semibold hover:bg-blue-100 transition-colors"
                    >
                      Mark all as read
                    </button>
                  </div>

                  <div className="glass-panel rounded-2xl overflow-hidden divide-y divide-slate-100 dark:divide-slate-800">
                    {notifications.length === 0 ? (
                      <div className="p-10 text-center text-slate-500">
                        <p className="text-sm font-semibold">No notifications available right now</p>
                        <p className="text-xs mt-1">System alerts and bot events will appear here.</p>
                      </div>
                    ) : (
                      notifications.map((n) => (
                      <div
                        key={n.id}
                        onClick={() => handleOpenNotification(n)}
                        className={`p-4 flex items-start justify-between gap-4 cursor-pointer transition-colors ${
                          !n.read
                            ? 'bg-blue-50/50 dark:bg-blue-950/20'
                            : 'hover:bg-slate-50 dark:hover:bg-slate-800/30'
                        }`}
                      >
                        <div>
                          <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                            {n.title}
                          </h4>
                          <p className="text-xs text-slate-600 dark:text-slate-300 mt-1">
                            {n.message}
                          </p>
                        </div>
                        <span className="text-[10px] text-slate-400 shrink-0 font-medium">
                          {n.time}
                        </span>
                      </div>
                    ))
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'Plans & Billing' && <PricingBillingView />}

              {activeTab === 'Admin' && user?.isAdmin && <AdminView />}

              {activeTab === 'Help' && <HelpSupportView mode="help" />}

              {activeTab === 'Support' && <HelpSupportView mode="support" />}
                </>
              )}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
