/** Safe localStorage / sessionStorage helpers — never throw on quota, private mode, or corrupt JSON. */

const APP_KEYS_PREFIXES = [
  'telebot_',
  'bm_',
  'bmp_',
];

export function safeGet(key: string, store: Storage | null = null): string | null {
  try {
    const s = store || (typeof localStorage !== 'undefined' ? localStorage : null);
    if (!s) return null;
    return s.getItem(key);
  } catch {
    return null;
  }
}

export function safeSet(key: string, value: string, store: Storage | null = null): void {
  try {
    const s = store || (typeof localStorage !== 'undefined' ? localStorage : null);
    if (!s) return;
    s.setItem(key, value);
  } catch {
    // quota / private mode
  }
}

export function safeRemove(key: string, store: Storage | null = null): void {
  try {
    const s = store || (typeof localStorage !== 'undefined' ? localStorage : null);
    if (!s) return;
    s.removeItem(key);
  } catch {}
}

export function safeJsonParse<T = any>(raw: string | null, fallback: T): T {
  if (raw == null || raw === '') return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function safeJsonGet<T = any>(key: string, fallback: T, store: Storage | null = null): T {
  return safeJsonParse<T>(safeGet(key, store), fallback);
}

/** Wipe BOT MATRIX keys only (theme optional). Call after a fatal boot error. */
export function clearBotMatrixStorage(opts?: { keepTheme?: boolean }): void {
  const keepTheme = opts?.keepTheme !== false;
  const theme = keepTheme ? safeGet('telebot_theme') : null;
  for (const store of [typeof localStorage !== 'undefined' ? localStorage : null, typeof sessionStorage !== 'undefined' ? sessionStorage : null]) {
    if (!store) continue;
    try {
      const keys: string[] = [];
      for (let i = 0; i < store.length; i++) {
        const k = store.key(i);
        if (k && APP_KEYS_PREFIXES.some((p) => k.startsWith(p))) keys.push(k);
      }
      keys.forEach((k) => {
        try { store.removeItem(k); } catch {}
      });
    } catch {}
  }
  if (theme) safeSet('telebot_theme', theme);
}

/** Validate and repair critical keys before React mounts. */
export function sanitizeBootStorage(): void {
  try {
    // Corrupt user blob
    const userRaw = safeGet('telebot_user');
    if (userRaw) {
      const u = safeJsonParse<any>(userRaw, null);
      if (!u || typeof u !== 'object' || (!u.id && !u.email)) {
        safeRemove('telebot_user');
      }
    }
    // Invalid tab name → reset
    const tab = safeGet('telebot_active_tab');
    const allowed = new Set([
      'Dashboard', 'My Bots', 'Bot Store', 'Plans & Billing', 'Broadcast Manager',
      'Recycle Bin', 'Transfers', 'Settings', 'Notifications', 'Help', 'Support', 'Admin',
    ]);
    if (tab && !allowed.has(tab)) safeRemove('telebot_active_tab');
  } catch {
    try { clearBotMatrixStorage(); } catch {}
  }
}
