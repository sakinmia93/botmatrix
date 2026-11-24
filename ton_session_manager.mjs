import TonConnect, { isWalletInfoRemote } from '@tonconnect/sdk';
import http from 'http';
import crypto from 'crypto';

class MapStorage {
  constructor() { this.map = new Map(); }
  async getItem(key) { return this.map.has(key) ? this.map.get(key) : null; }
  async setItem(key, value) { this.map.set(key, value); }
  async removeItem(key) { this.map.delete(key); }
}

const sessions = new Map();

function notifyPython(path, body) {
  const port = Number(process.env.API_PORT || 5001);
  const data = JSON.stringify(body);
  const req = http.request({
    host: '127.0.0.1', port, path, method: 'POST',
    headers: { 'content-type': 'application/json', 'content-length': Buffer.byteLength(data), 'x-bm-internal': process.env.BM_INTERNAL_TOKEN || 'bm-tc-internal' },
    timeout: 8000,
  }, (res) => res.resume());
  req.on('error', (e) => console.warn('[TC-Node] notifyPython', e.message));
  req.write(data); req.end();
}

function attachListener(st) {
  if (st.unsub) try { st.unsub(); } catch {}
  st.unsub = st.connector.onStatusChange((wallet) => {
    if (wallet && wallet.account) {
      st.status = 'connected';
      st.address = wallet.account.address;
      st.publicKey = wallet.account.publicKey || null;
      st.chain = String(wallet.account.chain || '-239');
      st.connectedAt = Date.now();
      console.log('[TC-Node] connected', st.meta.sessionId, st.address);
      notifyPython('/api/ton-connect/internal/status', {
        session_id: st.meta.sessionId, user_id: st.meta.userId, bot_id: st.meta.botId ?? null,
        status: 'connected', wallet_address: st.address, public_key: st.publicKey, chain: st.chain,
      });
    } else {
      st.status = 'disconnected'; st.address = null; st.publicKey = null; st.chain = null; st.connectedAt = null;
      console.log('[TC-Node] disconnected', st.meta.sessionId);
      notifyPython('/api/ton-connect/internal/status', {
        session_id: st.meta.sessionId, user_id: st.meta.userId, bot_id: st.meta.botId ?? null,
        status: 'pending', wallet_address: null,
      });
    }
  });
}

export async function createSession(opts) {
  const sessionId = opts.sessionId || crypto.randomBytes(16).toString('hex');
  const existing = sessions.get(sessionId);
  if (existing) {
    try { existing.unsub?.(); if (existing.connector.connected) await existing.connector.disconnect(); } catch {}
    sessions.delete(sessionId);
  }
  const storage = new MapStorage();
  const connector = new TonConnect({ manifestUrl: opts.manifestUrl, storage });
  const meta = {
    sessionId, userId: String(opts.userId), botId: opts.botId ?? null,
    botUsername: opts.botUsername, botLink: opts.botLink, manifestUrl: opts.manifestUrl,
    createdAt: Date.now(), exp: Date.now() + (opts.expirySeconds || 86400) * 1000,
  };
  const st = { meta, status: 'pending', address: null, publicKey: null, chain: null, connectedAt: null, connector, storage };
  attachListener(st);
  sessions.set(sessionId, st);
  try { await connector.restoreConnection(); } catch {}
  return { sessionId, status: st.status };
}

export function getSession(sessionId) {
  const st = sessions.get(sessionId);
  if (!st) return null;
  if (Date.now() > st.meta.exp) { void destroySession(sessionId); return null; }
  return {
    session_id: st.meta.sessionId, user_id: st.meta.userId,
    status: st.status === 'disconnected' ? 'pending' : st.status,
    wallet_address: st.address, public_key: st.publicKey, chain: st.chain,
    bot_username: st.meta.botUsername || 'BMPReferBot',
    bot_link: st.meta.botLink || 'https://t.me/BMPReferBot',
    connected_at: st.connectedAt, last_error: st.lastError || null,
  };
}

export async function listWallets(sessionId) {
  const st = sessions.get(sessionId);
  if (!st) throw new Error('Session not found');
  return st.connector.getWallets();
}

export async function connectWallet(sessionId, walletFilter = {}) {
  const st = sessions.get(sessionId);
  if (!st) throw new Error('Session not found');
  const wallets = await st.connector.getWallets();
  const remote = wallets.filter(isWalletInfoRemote);
  let target = remote.find((w) => w.name.toLowerCase().includes('tonkeeper')) || remote[0];
  if (walletFilter.appName) target = remote.find((w) => w.appName === walletFilter.appName) || target;
  else if (walletFilter.name) {
    const n = walletFilter.name.toLowerCase();
    target = remote.find((w) => w.name.toLowerCase().includes(n)) || target;
  }
  if (!target || !isWalletInfoRemote(target)) {
    return { universalLink: null, wallets: remote.map((w) => ({ name: w.name, appName: w.appName, universalLink: w.universalLink, bridgeUrl: w.bridgeUrl })) };
  }
  const link = st.connector.connect({ universalLink: target.universalLink, bridgeUrl: target.bridgeUrl });
  return { universalLink: typeof link === 'string' ? link : null, wallets: remote.map((w) => ({ name: w.name, appName: w.appName, universalLink: w.universalLink, bridgeUrl: w.bridgeUrl })) };
}

export async function connectSpecific(sessionId, universalLink, bridgeUrl) {
  const st = sessions.get(sessionId);
  if (!st) throw new Error('Session not found');
  const link = st.connector.connect({ universalLink, bridgeUrl });
  return typeof link === 'string' ? link : null;
}

export async function disconnectSession(sessionId) {
  const st = sessions.get(sessionId);
  if (!st) return false;
  try { if (st.connector.connected) await st.connector.disconnect(); } catch (e) { st.lastError = e.message; }
  st.status = 'disconnected'; st.address = null;
  notifyPython('/api/ton-connect/internal/status', {
    session_id: st.meta.sessionId, user_id: st.meta.userId, bot_id: st.meta.botId ?? null,
    status: 'pending', wallet_address: null,
  });
  return true;
}

export async function destroySession(sessionId) {
  const st = sessions.get(sessionId);
  if (!st) return;
  try { st.unsub?.(); if (st.connector.connected) await st.connector.disconnect(); } catch {}
  sessions.delete(sessionId);
}

export function sessionCount() { return sessions.size; }
