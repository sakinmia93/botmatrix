import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Menu,
  Bot,
  Search,
  Bell,
  RefreshCw,
  Check,
  ExternalLink,
  Shield,
  Activity,
  X,
  Sun,
  Moon,
} from 'lucide-react';
import { PageTab, NotificationItem, User } from '../types';

interface NavbarProps {
  activeTab: PageTab;
  subTitle?: string | null;
  onToggleSidebar: () => void;
  onRefreshData: () => void;
  isRefreshing: boolean;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  notifications: NotificationItem[];
  onMarkNotificationAsRead: (id: string) => void;
  onOpenNotification?: (n: NotificationItem) => void;
  user: User | null;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  subTitle,
  onToggleSidebar,
  onRefreshData,
  isRefreshing,
  searchQuery,
  setSearchQuery,
  notifications,
  onMarkNotificationAsRead,
  onOpenNotification,
  user,
  isDarkMode,
  onToggleTheme,
}) => {
  const [showNotifications, setShowNotifications] = useState(false);
  const notifPanelRef = useRef<HTMLDivElement | null>(null);
  // Close panel on outside tap / Escape — attach AFTER the opening gesture so mobile taps do not instantly close it
  useEffect(() => {
    if (!showNotifications) return;
    let active = true;
    const onDown = (ev: MouseEvent | TouchEvent) => {
      if (!active) return;
      const node = ev.target as Node;
      if (notifPanelRef.current && notifPanelRef.current.contains(node)) return;
      const btn = document.getElementById('navbar-notifications-btn');
      if (btn && btn.contains(node)) return;
      setShowNotifications(false);
    };
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setShowNotifications(false);
    };
    const timer = window.setTimeout(() => {
      document.addEventListener('mousedown', onDown);
      document.addEventListener('touchstart', onDown, { passive: true });
      document.addEventListener('keydown', onKey);
    }, 50);
    return () => {
      active = false;
      window.clearTimeout(timer);
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('touchstart', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [showNotifications]);
  const [searchFocused, setSearchFocused] = useState(false);

  const [customLogoUrl, setCustomLogoUrl] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('bot_matrix_platform_logo') || '/logo.jpg';
    }
    return null;
  });

  const unreadCount = (notifications || []).filter((n) => !n.read).length;

  return (
    <header className="sticky top-0 z-40 h-16 w-full max-w-[100vw] bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border-b border-slate-200/80 dark:border-slate-800/80 px-2 sm:px-4 lg:px-6 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-1.5 sm:gap-3 transition-colors">
      {/* LEFT: Sidebar Toggle Icon, Platform Logo, Platform Name */}
      <div className="flex items-center gap-1.5 sm:gap-3 min-w-0 shrink-0">
        {/* Sidebar Toggle Icon Button */}
        <motion.button
          id="navbar-sidebar-toggle-btn"
          type="button"
          onClick={onToggleSidebar}
          whileTap={{ scale: 0.92 }}
          className="p-2 rounded-xl text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 focus:outline-none transition-colors cursor-pointer shrink-0"
          title="Toggle Navigation Menu"
        >
          <Menu className="w-5 h-5" />
        </motion.button>

        {/* Platform Logo & Platform Name */}
        <div className="flex items-center gap-2 min-w-0">
          {customLogoUrl ? (
            <img
              src={customLogoUrl}
              alt="BOT MATRIX"
              className="w-8 h-8 rounded-xl object-contain shadow-md shrink-0"
              onError={() => setCustomLogoUrl(null)}
            />
          ) : (
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-cyan-500 flex items-center justify-center text-white shadow-md shadow-blue-500/25 ring-1 ring-white/20 shrink-0">
              <Bot className="w-4 h-4" />
            </div>
          )}
          <span className="font-black text-base sm:text-lg tracking-wider text-blue-600 dark:text-blue-400 font-mono uppercase hidden md:inline-block truncate max-w-[9rem]">
            BOT MATRIX
          </span>
        </div>
      </div>

      {/* CENTER: Name of the current active page — always truncates to fit */}
      <div className="flex items-center justify-center min-w-0 overflow-hidden px-0.5">
        <div className="px-2 sm:px-3.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700/80 flex items-center gap-1.5 sm:gap-2 shadow-xs min-w-0 max-w-full">
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse shrink-0" />
          <h2
            className="text-[11px] sm:text-sm font-bold text-slate-900 dark:text-slate-100 tracking-wide truncate min-w-0"
            title={subTitle || activeTab || undefined}
          >
            {subTitle || activeTab}
          </h2>
        </div>
      </div>

      {/* RIGHT: Notifications, Theme Switcher, Real-time Refresh Icon */}
      <div className="flex items-center gap-1 sm:gap-2 lg:gap-3 shrink-0 justify-end">
        {/* Notifications Icon with Badge & Popover */}
        <div className="relative">
          <motion.button
            id="navbar-notifications-btn"
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setShowNotifications((v) => !v);
            }}
            whileTap={{ scale: 0.92 }}
            className="relative p-2 rounded-xl text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
            title="Notifications"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-rose-500 ring-2 ring-white dark:ring-slate-900 animate-pulse" />
            )}
          </motion.button>

          {/* Notifications Dropdown — portal to body (never clipped) */}
          {showNotifications && createPortal(
            <div
              ref={notifPanelRef}
              id="navbar-notifications-panel"
              className="fixed left-3 right-3 sm:left-auto sm:right-4 top-[4.25rem] w-auto sm:w-96 max-h-[min(70dvh,28rem)] overflow-y-auto rounded-2xl bg-white dark:bg-slate-900 shadow-2xl border border-slate-200 dark:border-slate-700 p-4 z-[99999]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <Bell className="w-4 h-4 text-blue-500" />
                  <span className="font-bold text-sm text-slate-900 dark:text-white">Notifications</span>
                </div>
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-300">
                  {unreadCount} Unread
                </span>
              </div>

              <div className="max-h-72 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800 my-2">
                {(notifications || []).length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-500 font-medium">No notifications yet</div>
                ) : (
                  (notifications || []).map((n) => (
                    <div
                      key={n.id}
                      onClick={() => {
                        if (onOpenNotification) {
                          onOpenNotification(n);
                          setShowNotifications(false);
                        } else {
                          onMarkNotificationAsRead(n.id);
                        }
                      }}
                      className={`py-2.5 px-2 rounded-xl transition-colors cursor-pointer ${
                        !n.read ? 'bg-blue-50 dark:bg-blue-950/40' : 'hover:bg-slate-100 dark:hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-bold text-slate-900 dark:text-white break-words">{n.title}</p>
                        <span className="text-xs text-slate-600 dark:text-slate-400 font-medium shrink-0">{n.time}</span>
                      </div>
                      <p className="text-xs text-slate-700 dark:text-slate-300 mt-1 line-clamp-2 font-medium break-words">{n.message}</p>
                    </div>
                  ))
                )}
              </div>

              <div className="pt-2 border-t border-slate-200 dark:border-slate-800 flex justify-between items-center text-xs">
                <button
                  type="button"
                  onClick={() => { (notifications || []).forEach((n) => onMarkNotificationAsRead(n.id)); }}
                  className="text-blue-700 dark:text-blue-400 font-bold hover:underline cursor-pointer"
                >
                  Mark all read
                </button>
                <button
                  type="button"
                  onClick={() => setShowNotifications(false)}
                  className="text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 font-semibold cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>,
            document.body
          )}
        </div>

        {/* Theme Toggle (Light / Dark mode) */}
        <motion.button
          id="navbar-theme-toggle-btn"
          type="button"
          onClick={onToggleTheme}
          whileTap={{ scale: 0.88 }}
          className="p-2 rounded-xl text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
          title={isDarkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
        >
          {isDarkMode ? (
            <Sun className="w-5 h-5 text-amber-400" />
          ) : (
            <Moon className="w-5 h-5 text-slate-700" />
          )}
        </motion.button>

        {/* Real-time Refresh Icon at Top-Right */}
        <motion.button
          id="navbar-refresh-btn"
          type="button"
          onClick={onRefreshData}
          whileTap={{ scale: 0.88 }}
          className={`p-2 rounded-xl text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer ${
            isRefreshing ? 'text-blue-600 dark:text-blue-400' : ''
          }`}
          title="Refresh real-time bot data"
        >
          <RefreshCw className={`w-5 h-5 ${isRefreshing ? 'animate-spin text-blue-600' : ''}`} />
        </motion.button>
      </div>
    </header>
  );
};
