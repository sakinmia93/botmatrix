import { PlatformSettings } from '../types';
import { apiService } from '../services/apiService';

/** Server-backed settings: kept in memory, saved to the account on the server (debounced). */
export const defaultPlatformSettings: PlatformSettings = {
  email: '',
  apiKey: '',
  apiKeyCreatedAt: '',
  transferConfig: 'whitelist_auto',
  senderWhitelist: [],
  outgoingLimit: 10,
  allowBotCodeToDeleteBots: false,
  globalBotAdmins: [],
  activeSessions: [],
  emailNotifications: true,
  disableAnimations: false,
  plan: { name: 'Free', remainingPoints: 0, extraPoints: 0, resetsOn: '', changePlanTg: '', billingSupportTg: '' },
};

let cache: PlatformSettings = { ...defaultPlatformSettings };
let timer: any = null;

export function getPlatformSettings(userEmail?: string): PlatformSettings {
  return { ...cache, email: userEmail || cache.email };
}

export async function loadPlatformSettings(): Promise<PlatformSettings> {
  const s: any = await apiService.getSettings();
  if (s) {
    cache = {
      ...defaultPlatformSettings,
      ...s,
      senderWhitelist: Array.isArray(s.senderWhitelist) ? s.senderWhitelist : [],
      globalBotAdmins: Array.isArray(s.globalBotAdmins) ? s.globalBotAdmins : cache.globalBotAdmins,
      activeSessions: Array.isArray(s.activeSessions) ? s.activeSessions : [],
      plan: { ...defaultPlatformSettings.plan, ...(s.plan || {}) },
    };
  }
  return cache;
}

export function savePlatformSettings(settings: PlatformSettings): void {
  cache = settings;
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('telebot_settings_updated', { detail: settings }));
  clearTimeout(timer);
  timer = setTimeout(() => {
    const { activeSessions, email, apiKey, plan, globalBotAdmins, ...rest } = settings as any;
    apiService.updateSettings(rest as any).catch(() => {});
  }, 400);
}
