/**
 * Backend Data Integration Service for BOT MATRIX
 * Axios-powered client — all data from Python backend / PostgreSQL|SQLite.
 * No demo/mock fallbacks for core lists (bots, broadcasts, notifications).
 */
import axios, { AxiosError, AxiosRequestConfig } from 'axios';
import { BotItem, StoreBot, BroadcastItem, BotChatUser, PlatformSettings, NotificationItem, User } from '../types';

const API_BASE = '/api';

/** Persist session token: rememberMe → localStorage (survives browser restart); else sessionStorage only. */
export function setAuthToken(token: string, rememberMe: boolean) {
  try {
    if (rememberMe) {
      localStorage.setItem('telebot_auth_token', token);
      sessionStorage.removeItem('telebot_auth_token');
    } else {
      sessionStorage.setItem('telebot_auth_token', token);
      localStorage.removeItem('telebot_auth_token');
    }
  } catch {}
}

export function getAuthToken(): string | null {
  try {
    return sessionStorage.getItem('telebot_auth_token') || localStorage.getItem('telebot_auth_token');
  } catch {
    return null;
  }
}

export function clearAuthToken() {
  try {
    localStorage.removeItem('telebot_auth_token');
    sessionStorage.removeItem('telebot_auth_token');
    localStorage.removeItem('telebot_user');
  } catch {}
}


const http = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

http.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (res) => res,
  (error: AxiosError<any>) => {
    if (error.response?.status === 401) {
      const data = error.response.data || {};
      if (data.force_logout && typeof window !== 'undefined') {
        clearAuthToken();
        window.dispatchEvent(new CustomEvent('telebot_force_logout', { detail: data }));
      }
    }
    return Promise.reject(error);
  }
);

export function apiErrorMessage(err: any, fallback = 'Something went wrong. Please try again.'): string {
  const d = err?.response?.data;
  if (d && typeof d.error === 'string' && d.error) return d.error;
  if (err?.code === 'ECONNABORTED') return 'The request timed out. Please try again.';
  if (err?.message === 'Network Error') return 'Cannot reach the server. Check your connection.';
  return fallback;
}

export interface UsersJob {
  id: string; kind: 'import' | 'export'; state: 'running' | 'done' | 'cancelled' | 'error';
  processed: number; total: number; percent: number; elapsed: number; etaSeconds?: number; error?: string;
  imported?: number; existing?: number; unreachable?: number; failed?: number; ignored?: number; toVerify?: number;
  format?: 'json' | 'csv' | 'txt'; includeDates?: boolean; fields?: string[]; filter?: string; rows?: number; size?: number; filename?: string;
}

class ApiService {
  private async request<T>(
    endpoint: string,
    options?: { method?: string; body?: string; headers?: Record<string, string>; timeout?: number },
    fallback?: T,
  ): Promise<T> {
    try {
      const method = (options?.method || 'GET').toUpperCase();
      const config: AxiosRequestConfig = {
        url: endpoint,
        method: method as any,
        headers: options?.headers,
        timeout: options?.timeout,
      };
      if (options?.body) {
        config.data = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
      }
      const res = await http.request<T>(config);
      return res.data;
    } catch (err) {
      if (fallback !== undefined) {
        return fallback;
      }
      throw err;
    }
  }

  // 1. AUTHENTICATION & SECURITY
  async login(payload: { email: string; password: string; code?: string; remember_me: boolean; client_metadata: any }): Promise<{
    success: boolean;
    otpRequired?: boolean;
    token: string;
    user: User;
    remember_me: boolean;
  }> {
    return this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async register(payload: { email: string; password: string; name?: string; code?: string; client_metadata: any }): Promise<{
    success: boolean;
    otpRequired?: boolean;
    token: string;
    user: User;
  }> {
    return this.request('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async forgotPassword(email: string, captchaToken?: string): Promise<{ success: boolean; message: string; email: string; code?: string }> {
    return this.request('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email, captchaToken }),
    });
  }

  async resetPassword(payload: { email: string; code: string; new_password: string }): Promise<{ success: boolean; message: string }> {
    return this.request('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async logout(): Promise<{ success: boolean }> {
    try {
      return await this.request('/auth/logout', { method: 'POST' });
    } finally {
      if (typeof localStorage !== 'undefined') {
        clearAuthToken();
      }
    }
  }

  async getMe(): Promise<{ success: boolean; user: User } | null> {
    try {
      return await this.request('/auth/me', { method: 'GET' });
    } catch {
      return null;
    }
  }

  // 2. BOTS
  async sendChatMessage(botId: string, telegramId: string, text: string): Promise<{ success: boolean }> {
    return this.request(`/bots/${botId}/chats/${telegramId}/send`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    });
  }

  async getBots(): Promise<BotItem[]> {
    return this.request<BotItem[]>('/bots', { method: 'GET' });
  }

  async createBot(botData: Partial<BotItem>): Promise<BotItem> {
    // Telegram identity check can take several seconds — do not use the default 20s client timeout
    return this.request<BotItem>('/bots', {
      method: 'POST',
      body: JSON.stringify(botData),
      timeout: 90000,
    });
  }

  async updateBot(bot: Partial<BotItem> & { id: string }): Promise<BotItem> {
    // never send read-only / derived fields back to the server
    const { chats, errors, tokenMasked, hasToken, activeUsers, totalCommands, lastActive, uptime, status, photoUrl, botNumericId, username, ...rest } = bot as any;
    return this.request<BotItem>(`/bots/${bot.id}`, {
      method: 'PUT',
      body: JSON.stringify(rest),
    });
  }

  async getBotIntro(id: string): Promise<any> {
    return this.request(`/bots/${id}/intro?tz=${-new Date().getTimezoneOffset()}`, { method: 'GET' });
  }

  async getBotErrors(id: string): Promise<any[]> {
    return this.request(`/bots/${id}/errors`, { method: 'GET' });
  }

  async clearBotErrors(id: string): Promise<any> {
    return this.request(`/bots/${id}/errors`, { method: 'DELETE' });
  }

  async getBot(id: string): Promise<BotItem> {
    return this.request<BotItem>(`/bots/${id}`, { method: 'GET' });
  }

  async transferBot(botId: string, email: string, options?: { data?: boolean; chats?: boolean; errors?: boolean; env?: boolean }): Promise<{ success: boolean; transfer: any }> {
    return this.request(`/bots/${botId}/transfer`, { method: 'POST', body: JSON.stringify({ email, options: options || {} }) });
  }

  async getTransfers(): Promise<{ incoming: any[]; outgoing: any[]; history: any[]; limits: any }> {
    return this.request('/transfers', { method: 'GET' });
  }

  async respondTransfer(id: string, action: 'accept' | 'reject' | 'cancel'): Promise<{ success: boolean; transfer: any }> {
    return this.request(`/transfers/${id}/${action}`, { method: 'POST' });
  }

  async getEditorCatalog(): Promise<any> {
    return this.request('/editor/catalog', { method: 'GET' });
  }

  async validateCode(code: string): Promise<{ ok: boolean; errors: { line: number; col: number; endCol?: number; message: string; severity: string }[] }> {
    return this.request('/editor/validate', { method: 'POST', body: JSON.stringify({ code }) });
  }

  async formatCode(code: string): Promise<{ ok: boolean; code?: string; changed?: boolean; error?: string }> {
    return this.request('/editor/format', { method: 'POST', body: JSON.stringify({ code }) });
  }

  async testCommand(botId: string, payload: {
    name: string;
    code?: string;
    text?: string;
    callbackData?: string;
    update_type?: string;
    updateType?: string;
    currency?: string;
    total_amount?: number;
    invoice_payload?: string;
    payload?: Record<string, unknown>;
  }): Promise<{
    ok: boolean; error?: string; aborted: boolean; durationMs: number; calls: { method: string; params: any }[]; logs: string[];
  }> {
    return this.request(`/bots/${botId}/test-command`, { method: 'POST', body: JSON.stringify(payload) });
  }

  async getStatus(): Promise<any> {
    return this.request('/status', { method: 'GET' });
  }

  async getPlans(): Promise<{ plans: any[]; current: string; points: number; contactUrl: string }> {
    return this.request('/plans', { method: 'GET' });
  }

  async getTransferReceiptCode(id: string): Promise<{ code: string }> {
    return this.request(`/transfers/${encodeURIComponent(id)}/receipt`, { method: 'GET' });
  }

  async getPublicReceipt(code: string): Promise<any> {
    const r = await fetch(`/api/public/receipt/${encodeURIComponent(code)}`);
    return r.json();
  }

  async getDashboardStats(): Promise<{ totals: any; activity: { time: string; users: number; commands: number }[] }> {
    return this.request('/dashboard/stats', { method: 'GET' });
  }

  async createTelegramLinkCode(): Promise<{ code: string; url: string; expiresInSec: number }> {
    return this.request('/telegram/link-code', { method: 'POST' });
  }

  async updateTelegramAlerts(alerts: Record<string, boolean>): Promise<{ success: boolean; alerts: Record<string, boolean> }> {
    return this.request('/telegram/alerts', { method: 'POST', body: JSON.stringify({ alerts }) });
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<{ success: boolean }> {
    return this.request('/auth/change-password', { method: 'POST', body: JSON.stringify({ currentPassword, newPassword }) });
  }

  async deleteAccount(password: string): Promise<{ success: boolean }> {
    return this.request('/account/delete', { method: 'POST', body: JSON.stringify({ password }) });
  }

  async deleteBot(id: string): Promise<{ success: boolean; id: string }> {
    return this.request<{ success: boolean; id: string }>(`/bots/${id}`, {
      method: 'DELETE',
    });
  }

  async toggleBotStatus(id: string): Promise<BotItem> {
    return this.request<BotItem>(`/bots/${id}/toggle-status`, {
      method: 'POST',
    });
  }

  // 3. FOLDERS
  async getFolders(): Promise<string[]> {
    return this.request<string[]>('/folders', { method: 'GET' }, []);
  }

  async addFolder(name: string): Promise<string[]> {
    return this.request<string[]>('/folders', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  // 4. GLOBAL BOT ADMINS
  async getGlobalAdmins(): Promise<string[]> {
    return this.request<string[]>('/global-admins', { method: 'GET' }, []);
  }

  async addGlobalAdmin(telegramId: string): Promise<string[]> {
    return this.request<string[]>('/global-admins', {
      method: 'POST',
      body: JSON.stringify({ telegramId }),
    });
  }

  async removeGlobalAdmin(telegramId: string): Promise<string[]> {
    return this.request<string[]>(`/global-admins/${telegramId}`, {
      method: 'DELETE',
    });
  }

  // 5. BOT STORE
  async getStoreBots(): Promise<StoreBot[]> {
    return this.request<StoreBot[]>('/store/bots', { method: 'GET' }, []);
  }

  async cloneStoreBot(storeBotId: string): Promise<{ success: boolean; bot: BotItem }> {
    return this.request<{ success: boolean; bot: BotItem }>(`/store/bots/${storeBotId}/clone`, {
      method: 'POST',
    });
  }

  // 6. BROADCASTS
  async getBotAdminOverview(id: string, days: number): Promise<any> {
    return this.request(`/bots/${id}/admin/overview?days=${days}`, { method: 'GET' });
  }

  async setBotMaintenance(id: string, on: boolean, message: string): Promise<any> {
    return this.request(`/bots/${id}/admin/maintenance`, { method: 'PUT', body: JSON.stringify({ on, message }) });
  }

  async botAdminAction(id: string, action: string): Promise<{ ok: boolean; message: string }> {
    return this.request(`/bots/${id}/admin/action`, { method: 'POST', body: JSON.stringify({ action }) });
  }

  async getBroadcasts(): Promise<BroadcastItem[]> {
    return this.request<BroadcastItem[]>('/broadcasts', { method: 'GET' });
  }

  async createBroadcast(broadcast: Partial<BroadcastItem>): Promise<BroadcastItem> {
    return this.request<BroadcastItem>('/broadcasts', {
      method: 'POST',
      body: JSON.stringify(broadcast),
    });
  }

  async uploadBroadcastMedia(file: File, messageType: string): Promise<{ mediaId: string; name: string }> {
    const res = await http.post('/broadcasts/media', file, {
      headers: { 'Content-Type': file.type || 'application/octet-stream', 'x-file-name': encodeURIComponent(file.name), 'x-media-type': messageType },
      timeout: 180000,
      transformRequest: [(d: any) => d],
    });
    return res.data;
  }

  // ---- audience import / export + token reveal
  async importUsers(botId: string, file: File): Promise<UsersJob> {
    const res = await http.post(`/bots/${botId}/users/import`, file, {
      headers: { 'Content-Type': 'application/octet-stream', 'x-file-name': encodeURIComponent(file.name) },
      timeout: 180000,
      transformRequest: [(d: any) => d],
    });
    return res.data;
  }
  async exportUsers(botId: string, opts: { format: 'json' | 'csv' | 'txt'; fields: string[]; filter: string }): Promise<UsersJob> {
    return this.request(`/bots/${botId}/users/export`, { method: 'POST', body: JSON.stringify(opts) });
  }
  private saveBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }
  async exportBotPackage(botId: string, format: string, parts: string[], envValues: boolean): Promise<string> {
    const res = await http.get(`/bots/${botId}/export`, { params: { format, parts: parts.join(','), envValues: envValues ? 1 : 0 }, responseType: 'blob', timeout: 180000 });
    const cd = String(res.headers['content-disposition'] || '');
    const fn = (/filename="?([^";]+)"?/.exec(cd) || [])[1] || `bot_export.${format}`;
    this.saveBlob(res.data, fn);
    return fn;
  }
  async importBotPackage(botId: string, file: File, opts: { parts?: string[]; replace?: boolean; dryRun?: boolean }): Promise<any> {
    const res = await http.post(`/bots/${botId}/import`, file, {
      params: { parts: opts.parts?.join(','), replace: opts.replace ? 1 : 0, dryRun: opts.dryRun ? 1 : 0 },
      headers: { 'Content-Type': 'application/octet-stream', 'x-file-name': encodeURIComponent(file.name) },
      timeout: 180000,
      transformRequest: [(d: any) => d],
    });
    return res.data;
  }
  async usersJobs(botId: string): Promise<{ import?: UsersJob; export?: UsersJob }> {
    return this.request(`/bots/${botId}/users/jobs`, { method: 'GET' });
  }
  async usersJob(botId: string, jobId: string): Promise<UsersJob> {
    return this.request(`/bots/${botId}/users/jobs/${jobId}`, { method: 'GET' });
  }
  async cancelUsersJob(botId: string, jobId: string): Promise<UsersJob> {
    return this.request(`/bots/${botId}/users/jobs/${jobId}/cancel`, { method: 'POST', body: JSON.stringify({}) });
  }
  async downloadUsersExport(botId: string, job: UsersJob): Promise<void> {
    const res = await http.get(`/bots/${botId}/users/export/${job.id}/download`, { responseType: 'blob', timeout: 180000 });
    this.saveBlob(res.data, job.filename || `users.${job.format || 'json'}`);
  }
  async revealBotToken(botId: string): Promise<string> {
    const r = await this.request<{ token: string }>(`/bots/${botId}/token`, { method: 'GET' });
    return r.token;
  }

  async detectBroadcastUrl(url: string): Promise<{ type: string; url: string; caption?: string; parseMode?: 'HTML' | null; note?: string; buttons?: any[]; customEmojiIds?: string[] }> {
    return this.request('/broadcasts/detect-url', { method: 'POST', body: JSON.stringify({ url }) });
  }

  async api<T = any>(method: 'GET' | 'POST' | 'PUT', path: string, body?: any): Promise<T> {
    return this.request<T>(path, { method, ...(method === 'GET' ? {} : { body: JSON.stringify(body ?? {}) }) });
  }

  async adminGet<T = any>(path: string): Promise<T> {
    return this.request<T>(`/admin/${path}`, { method: 'GET' });
  }

  async adminPut<T = any>(path: string, body: any): Promise<T> {
    return this.request<T>(`/admin/${path}`, { method: 'PUT', body: JSON.stringify(body) });
  }

  async adminDelete<T = any>(path: string): Promise<T> {
    return this.request<T>(`/admin/${path}`, { method: 'DELETE' });
  }

  async adminPost<T = any>(path: string, body: any): Promise<T> {
    return this.request<T>(`/admin/${path}`, { method: 'POST', body: JSON.stringify(body) });
  }

  async getBroadcastLanguages(botIds: string[]): Promise<{ code: string; count: number }[]> {
    return this.request(`/broadcasts/languages?botIds=${encodeURIComponent(botIds.join(','))}`, { method: 'GET' });
  }

  async getBroadcast(id: string): Promise<BroadcastItem> {
    return this.request<BroadcastItem>(`/broadcasts/${id}`, { method: 'GET' });
  }

  async updateBroadcastSpeed(id: string, speed: string): Promise<{ success: boolean; id: string; deliverySpeed: string }> {
    return this.request<{ success: boolean; id: string; deliverySpeed: string }>(`/broadcasts/${id}/speed`, {
      method: 'POST',
      body: JSON.stringify({ speed }),
    });
  }

  async deleteBroadcast(id: string): Promise<{ success: boolean; id: string }> {
    return this.request<{ success: boolean; id: string }>(`/broadcasts/${id}`, {
      method: 'DELETE',
    });
  }

  async pauseBroadcast(id: string): Promise<{ success: boolean; id: string; status: string }> {
    return this.request<{ success: boolean; id: string; status: string }>(`/broadcasts/${id}/pause`, {
      method: 'POST',
    });
  }

  async resumeBroadcast(id: string): Promise<{ success: boolean; id: string; status: string }> {
    return this.request<{ success: boolean; id: string; status: string }>(`/broadcasts/${id}/resume`, {
      method: 'POST',
    });
  }

  async cancelBroadcast(id: string): Promise<{ success: boolean; id: string; status: string }> {
    return this.request<{ success: boolean; id: string; status: string }>(`/broadcasts/${id}/cancel`, {
      method: 'POST',
    });
  }

  async updateBroadcastBotStatus(broadcastId: string, botId: string, status: string): Promise<{
    success: boolean;
    id: string;
    botId: string;
    botStatus: string;
    status: string;
    botStats: any[];
  }> {
    return this.request<{
      success: boolean;
      id: string;
      botId: string;
      botStatus: string;
      status: string;
      botStats: any[];
    }>(`/broadcasts/${broadcastId}/bots/${botId}/status`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    });
  }

  async getBroadcastMinUsers(): Promise<{ minBroadcastUsers: number }> {
    return this.request<{ minBroadcastUsers: number }>('/settings/broadcast-limit', { method: 'GET' });
  }

  async updateBroadcastMinUsers(minBroadcastUsers: number): Promise<{ success: boolean; minBroadcastUsers: number }> {
    return this.request<{ success: boolean; minBroadcastUsers: number }>('/settings/broadcast-limit', {
      method: 'POST',
      body: JSON.stringify({ minBroadcastUsers }),
    });
  }

  async syncBotWithTelegram(botId: string, name?: string): Promise<{ success: boolean; id: string; name: string; username: string; photoUrl?: string; botNumericId?: string }> {
    return this.request<{ success: boolean; id: string; name: string; username: string; photoUrl?: string }>(`/bots/${botId}/sync-telegram`, {
      method: 'POST',
      body: JSON.stringify({ name: name || '' }),
    });
  }

  async refreshBotProfilePhoto(botId: string): Promise<{ success: boolean; id: string; photoUrl: string }> {
    return this.request<{ success: boolean; id: string; photoUrl: string }>(`/bots/${botId}/refresh-photo`, {
      method: 'POST',
    });
  }

  async cleanFailedBroadcast(id: string): Promise<{ success: boolean; id: string }> {
    return this.request<{ success: boolean; id: string }>(`/broadcasts/${id}/clean-failed`, {
      method: 'POST',
    });
  }

  // 7. AUDIENCE CHATS
  async getAudienceUsers(botId: string, params?: { page?: number; limit?: number; search?: string; filter?: string }): Promise<{
    users: BotChatUser[];
    total: number;
    page: number;
    totalPages: number;
    counts?: { all: number; active: number; blocked: number; leftBot: number };
  }> {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', params.page.toString());
    if (params?.limit) query.set('limit', params.limit.toString());
    if (params?.search) query.set('search', params.search);
    if (params?.filter) query.set('filter', params.filter);

    return this.request(`/chats/${botId}?${query.toString()}`, { method: 'GET' }, {
      users: [],
      total: 0,
      page: 1,
      totalPages: 1,
    });
  }

  async toggleBlockUser(botId: string, userId: string): Promise<{ success: boolean; isBlocked: boolean }> {
    return this.request<{ success: boolean; isBlocked: boolean }>(`/chats/${botId}/users/${userId}/block`, {
      method: 'PUT',
    });
  }

  async sendDirectReply(botId: string, userId: string, message: string): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>(`/chats/${botId}/users/${userId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  }

  // 8. DATABASE
  async getBotDatabase(botId: string, q: { scope: 'bot' | 'user'; page?: number; limit?: number; search?: string; userId?: string }): Promise<any> {
    return this.request(`/database/${botId}?${new URLSearchParams(Object.entries(q).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)])).toString()}`, { method: 'GET' });
  }
  async saveBotDatabaseRow(botId: string, row: { scope: 'bot' | 'user'; key: string; value: string; type: string; userId?: string }): Promise<{ success: boolean }> {
    return this.request(`/database/${botId}`, { method: 'PUT', body: JSON.stringify(row) });
  }
  async deleteBotDatabaseRow(botId: string, q: { scope: 'bot' | 'user'; key: string; userId?: string }): Promise<{ success: boolean }> {
    return this.request(`/database/${botId}?${new URLSearchParams(Object.entries(q).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString()}`, { method: 'DELETE' });
  }

  // 9. RECYCLE BIN
  async getRecycleBin(): Promise<any[]> {
    return this.request('/recycle-bin', { method: 'GET' });
  }

  async restoreBotFromRecycleBin(id: string): Promise<any> {
    return this.request(`/recycle-bin/${id}/restore`, { method: 'POST' });
  }

  async permanentlyDeleteBot(id: string): Promise<{ success: boolean; deleted?: string; error?: string }> {
    return this.request(`/recycle-bin/${id}`, { method: 'DELETE' });
  }

  // 10. NOTIFICATIONS
  async getNotifications(): Promise<NotificationItem[]> {
    return this.request<NotificationItem[]>('/notifications', { method: 'GET' });
  }

  async markNotificationRead(id: string): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>(`/notifications/${id}/read`, {
      method: 'PUT',
    });
  }

  async markAllNotificationsRead(): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>('/notifications/read-all', { method: 'POST' });
  }

  // 11. SETTINGS
  async getSettings(): Promise<PlatformSettings | null> {
    return this.request<PlatformSettings | null>('/settings', { method: 'GET' }, null);
  }

  async updateSettings(settings: PlatformSettings): Promise<PlatformSettings> {
    return this.request<PlatformSettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    });
  }

  // 12. SUPPORT TICKET (full conversation system)
  async submitSupportTicket(ticket: {
    name?: string;
    email?: string;
    message: string;
    subject?: string;
    department?: string;
    category?: string;
    priority?: string;
    trackId?: string;
  }): Promise<{ success: boolean; ticketId: string }> {
    return this.request<{ success: boolean; ticketId: string }>('/help-support/ticket', {
      method: 'POST',
      body: JSON.stringify(ticket),
    });
  }

  async getSupportTickets(): Promise<any[]> {
    return this.request<any[]>('/help-support/tickets', { method: 'GET' }, []);
  }

  async getSupportTicket(id: string): Promise<any> {
    return this.request<any>(`/help-support/tickets/${encodeURIComponent(id)}`, { method: 'GET' });
  }

  async replySupportTicket(id: string, message: string): Promise<{ success: boolean; replyId: string; status: string }> {
    return this.request<{ success: boolean; replyId: string; status: string }>(
      `/help-support/tickets/${encodeURIComponent(id)}/reply`,
      { method: 'POST', body: JSON.stringify({ message }) },
    );
  }

  
  async supportTyping(id: string, typing: boolean): Promise<any> {
    return this.request(`/help-support/tickets/${encodeURIComponent(id)}/typing`, {
      method: 'POST',
      body: JSON.stringify({ typing }),
    });
  }

  async adminSupportTyping(id: string, typing: boolean): Promise<any> {
    return this.adminPost(`tickets/${encodeURIComponent(id)}/typing`, { typing });
  }

  async closeSupportTicket(id: string): Promise<{ success: boolean; status: string }> {
    return this.request<{ success: boolean; status: string }>(
      `/help-support/tickets/${encodeURIComponent(id)}/close`,
      { method: 'POST', body: JSON.stringify({}) },
    );
  }

  async reopenSupportTicket(id: string): Promise<{ success: boolean; status: string }> {
    return this.request<{ success: boolean; status: string }>(
      `/help-support/tickets/${encodeURIComponent(id)}/reopen`,
      { method: 'POST', body: JSON.stringify({}) },
    );
  }

  // 13. USER POINTS BALANCE & DEDUCTION
  async getPoints(): Promise<{ points: number; plan: string; allBotsStopped: boolean }> {
    return this.request<{ points: number; plan: string; allBotsStopped: boolean }>('/user/points', { method: 'GET' });
  }

  // 14. TELEGRAM CONNECT (through the connect bot)
  async getTelegramStatus(): Promise<{
    connected: boolean; username: string; firstName?: string; telegramId?: string; connectedAt?: string;
    connectBotUsername?: string; connectBotLink?: string; available?: boolean;
    alerts: Record<string, boolean>;
    account?: { name: string; email: string; plan: string; points: number; botsTotal: number; botsRunning: number;
      activeBroadcast: { id: string; title: string; status: string; percent: number } | null };
  }> {
    return this.request('/telegram/status', { method: 'GET' });
  }

  async disconnectTelegram(): Promise<{ success: boolean; connected: boolean }> {
    return this.request('/telegram/disconnect', { method: 'POST' });
  }

  async sendTelegramTestAlert(): Promise<{ success: boolean; message: string }> {
    return this.request('/telegram/test-alert', { method: 'POST' });
  }

  // SETTINGS: API key & sessions
  async regenerateApiKey(): Promise<{ apiKey: string; apiKeyMasked?: string; apiKeyCreatedAt: string; warning?: string }> {
    return this.request('/settings/api-key', { method: 'POST' });
  }

  async revokeSession(id: string): Promise<{ success: boolean }> {
    return this.request(`/sessions/${id}`, { method: 'DELETE' });
  }

  async revokeOtherSessions(): Promise<{ success: boolean }> {
    return this.request('/sessions/revoke-others', { method: 'POST' });
  }

  async revokeAllSessions(): Promise<{ success: boolean; force_logout?: boolean }> {
    return this.request('/sessions/revoke-all', { method: 'POST' });
  }
}

export const apiService = new ApiService();
