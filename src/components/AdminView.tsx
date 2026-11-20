import React, { useCallback, useEffect, useState, useRef } from 'react';
import { motion } from 'motion/react';
import { SupportChat } from './SupportChat';
import { Server, Skull, LayoutDashboard, Users as UsersIc, CreditCard, Database as DbIc, ScrollText, ShieldCheck, Store, Settings as SetIc, LifeBuoy, Languages } from 'lucide-react';
import { apiService } from '../services/apiService';
import { ServerPanel, FleetPanel, DatabasePanel, LogsPanel, SecurityPanel, t, Lang } from './AdminPanels';

type Tab = 'Server' | 'Fleet' | 'Overview' | 'Users' | 'Plans' | 'Database' | 'Logs' | 'Security' | 'Store' | 'Settings' | 'Tickets';
const TABS: Tab[] = ['Server', 'Fleet', 'Overview', 'Users', 'Plans', 'Database', 'Logs', 'Security', 'Store', 'Settings', 'Tickets'];
const TAB_ICON: Record<Tab, any> = { Server: Server, Fleet: Skull, Overview: LayoutDashboard, Users: UsersIc, Plans: CreditCard, Database: DbIc, Logs: ScrollText, Security: ShieldCheck, Store: Store, Settings: SetIc, Tickets: LifeBuoy };
const TAB_GRAD: Record<Tab, string> = { Server: 'from-indigo-500 to-violet-500', Fleet: 'from-rose-500 to-orange-500', Overview: 'from-sky-500 to-blue-600', Users: 'from-emerald-500 to-teal-500', Plans: 'from-amber-500 to-yellow-500', Database: 'from-fuchsia-500 to-pink-500', Logs: 'from-slate-600 to-slate-800', Security: 'from-green-500 to-emerald-600', Store: 'from-cyan-500 to-sky-500', Settings: 'from-purple-500 to-indigo-500', Tickets: 'from-orange-500 to-red-500' };
const card = 'rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4';
const inp = 'px-3 py-2 rounded-xl text-xs bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white';
const btn = 'px-3 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white cursor-pointer disabled:opacity-50';
const errMsg = (e: any) => e?.response?.data?.error || e?.message || 'Something went wrong';

const Overview: React.FC = () => {
  const [d, setD] = useState<any>(null);
  const [e, setE] = useState('');
  useEffect(() => { apiService.adminGet('overview').then(setD).catch((x) => setE(errMsg(x))); }, []);
  if (e) return <p className="text-xs text-red-500">{e}</p>;
  if (!d) return <p className="text-xs text-slate-500">Loading…</p>;
  const tiles = [['Users', d.users], ['New (7 days)', d.newUsers7d], ['Bots', d.bots], ['Broadcasts', d.broadcasts], ['Running now', d.activeBroadcasts], ['Open tickets', d.openTickets]];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {tiles.map(([k, v]) => (<div key={k as string} className={card}><div className="text-[11px] text-slate-500 font-bold">{k}</div><div className="text-2xl font-black text-slate-900 dark:text-white">{Number(v).toLocaleString()}</div></div>))}
      </div>
      <div className={card}>
        <div className="text-xs font-black mb-2 text-slate-700 dark:text-slate-300">Users per plan</div>
        {Object.entries(d.perPlan || {}).map(([p, n]) => (<div key={p} className="flex justify-between text-xs py-1"><span>{p}</span><b>{String(n)}</b></div>))}
      </div>
    </div>
  );
};

const Users: React.FC = () => {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [d, setD] = useState<any>({ users: [], total: 0 });
  const [plans, setPlans] = useState<any[]>([]);
  const [msg, setMsg] = useState('');
  const load = useCallback(() => {
    apiService.adminGet(`users?q=${encodeURIComponent(q)}&page=${page}`).then(setD).catch((x) => setMsg(errMsg(x)));
  }, [q, page]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { apiService.getPlans().then((r) => setPlans(r.plans)).catch(() => {}); }, []);
  const upd = async (id: string, body: any) => {
    try { await apiService.adminPut(`users/${id}`, body); setMsg('Saved'); load(); } catch (x) { setMsg(errMsg(x)); }
  };
  return (
    <div className="space-y-3">
      <div className="flex gap-2 items-center">
        <input className={inp + ' flex-1'} placeholder="Search name or e-mail" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <span className="text-[11px] text-slate-500">{d.total} users</span>
      </div>
      {msg && <p className="text-[11px] text-blue-600">{msg}</p>}
      <div className="space-y-2">
        {d.users.map((u: any) => (
          <div key={u.id} className={card + ' flex flex-wrap items-center gap-2 text-xs'}>
            <div className="min-w-0 flex-1"><div className="font-bold truncate">{u.name}</div><div className="text-slate-500 truncate">{u.email} · {u.bots} bots</div></div>
            <button className={btn.replace('bg-blue-600 hover:bg-blue-700', u.suspended ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-rose-600 hover:bg-rose-700')} onClick={() => { if (u.suspended) upd(u.id, { suspended: false }); else { const r = window.prompt('Suspend ' + u.email + '? They are signed out and their bots stop. Reason (optional):', ''); if (r !== null) upd(u.id, { suspended: true, reason: r }); } }}>{u.suspended ? 'Unsuspend' : 'Suspend'}</button>
            <select className={inp} value={u.plan} onChange={(e) => upd(u.id, { plan: e.target.value })}>{plans.map((p) => <option key={p.id}>{p.name}</option>)}</select>
            <b className="w-32 text-right font-mono" title="plan + extra">{(u.points - (u.extraPoints || 0)).toLocaleString()} + {(u.extraPoints || 0).toLocaleString()} extra</b>
            <form onSubmit={(e) => { e.preventDefault(); const v = (e.currentTarget.elements.namedItem('pts') as HTMLInputElement); if (v.value) { upd(u.id, { addPoints: Number(v.value) }); v.value = ''; } }} className="flex gap-1">
              <input name="pts" type="number" placeholder="± plan points" className={inp + ' w-28'} /><button className={btn}>Add</button>
            </form>
            <form onSubmit={(e) => { e.preventDefault(); const v = (e.currentTarget.elements.namedItem('xp') as HTMLInputElement); if (v.value) { upd(u.id, { addExtraPoints: Number(v.value) }); v.value = ''; } }} className="flex gap-1">
              <input name="xp" type="number" placeholder="± extra points" className={inp + ' w-28'} /><button className={btn}>Add extra</button>
            </form>
          </div>
        ))}
      </div>
      <div className="flex gap-2"><button className={btn} disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button><button className={btn} disabled={page * 25 >= d.total} onClick={() => setPage(page + 1)}>Next</button></div>
    </div>
  );
};

const LIMIT_LABELS: Record<string, string> = {
  maxBots: 'Max bots (-1 = unlimited)', maxCommandsPerBot: 'Commands per bot', maxBroadcastUsers: 'Broadcast audience (-1 = unlimited)', broadcastSpeed: 'Broadcast speed / sec (1000 = unlimited)',
};
const Plans: React.FC = () => {
  const [plans, setPlans] = useState<any[]>([]);
  const [msg, setMsg] = useState('');
  useEffect(() => { apiService.getPlans().then((r) => setPlans(r.plans)).catch((x) => setMsg(errMsg(x))); }, []);
  const set = (i: number, patch: any) => setPlans(plans.map((p, j) => (j === i ? { ...p, ...patch } : p)));
  const save = async (p: any) => {
    try { await apiService.adminPut(`plans/${p.id}`, { priceUsd: Number(p.priceUsd), points: Number(p.points), limits: p.limits, features: p.features }); setMsg(`${p.name} saved`); } catch (x) { setMsg(errMsg(x)); }
  };
  return (
    <div className="space-y-3">
      {msg && <p className="text-[11px] text-blue-600">{msg}</p>}
      {plans.map((p, i) => (
        <div key={p.id} className={card + ' space-y-3'}>
          <div className="font-black text-sm">{p.name}</div>
          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <label className="font-bold text-slate-500">Price (USD / month)<input type="number" min={0} className={inp + ' w-full mt-1'} value={p.priceUsd} onChange={(e) => set(i, { priceUsd: e.target.value })} /></label>
            <label className="font-bold text-slate-500">Points<input type="number" min={0} className={inp + ' w-full mt-1'} value={p.points} onChange={(e) => set(i, { points: e.target.value })} /></label>
            {Object.keys(LIMIT_LABELS).map((k) => (
              <label key={k} className="font-bold text-slate-500">{LIMIT_LABELS[k]}<input type="number" className={inp + ' w-full mt-1'} value={p.limits[k] ?? 0} onChange={(e) => set(i, { limits: { ...p.limits, [k]: Number(e.target.value) } })} /></label>
            ))}
          </div>
          <div className="flex flex-wrap gap-3 text-[11px]">
            {Object.keys(p.limits).filter((k) => typeof p.limits[k] === 'boolean').map((k) => (
              <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={!!p.limits[k]} onChange={(e) => set(i, { limits: { ...p.limits, [k]: e.target.checked } })} />{k}</label>
            ))}
          </div>
          <label className="block text-[11px] font-bold text-slate-500">What the plan shows (one per line)
            <textarea rows={5} className={inp + ' w-full mt-1 font-sans'} value={(p.features || []).join('\n')} onChange={(e) => set(i, { features: e.target.value.split('\n').filter(Boolean) })} />
          </label>
          <button className={btn} onClick={() => save(p)}>Save {p.name}</button>
        </div>
      ))}
    </div>
  );
};

const Settings: React.FC = () => {
  const [items, setItems] = useState<any[]>([]);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState('');
  const load = () => apiService.adminGet('config').then((r) => { setItems(r); setVals({}); }).catch((x) => setMsg(errMsg(x)));
  useEffect(() => { load(); }, []);
  const save = async () => {
    try {
      const r = await apiService.adminPut('config', { values: vals });
      setMsg(r.restartNeeded ? 'Saved. Some changes need a restart of the server to take effect.' : 'Saved and applied.');
      load();
    } catch (x) { setMsg(errMsg(x)); }
  };
  const groups = Array.from(new Set(items.map((i) => i.group)));
  return (
    <div className="space-y-4">
      <p className="text-[11px] text-slate-500">Everything the server reads from .env can be changed here. Values saved here win over .env. Secrets are never shown — leave blank to keep, type <b>-</b> to clear.</p>
      {groups.map((g) => (
        <div key={g} className={card + ' space-y-3'}>
          <div className="text-xs font-black text-slate-700 dark:text-slate-300">{g}</div>
          {items.filter((i) => i.group === g).map((i) => {
            const v = vals[i.key] ?? (i.kind === 'secret' || i.kind === 'readonly' ? '' : i.value);
            return (
              <label key={i.key} className="block text-[11px] font-bold text-slate-500">
                <span className="flex flex-wrap items-center gap-2">{i.label}
                  <span className="font-mono font-normal text-slate-400">{i.key}</span>
                  {i.restart && <span className="px-1.5 rounded bg-amber-100 text-amber-700 font-bold">restart</span>}
                  <span className={`px-1.5 rounded font-bold ${i.set ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500'}`}>{i.set ? `set · ${i.source}` : 'not set'}</span>
                </span>
                {i.kind === 'bool' ? (
                  <select className={inp + ' mt-1'} value={['1', 'true', 'on'].includes(String(v).toLowerCase()) ? '1' : '0'} onChange={(e) => setVals({ ...vals, [i.key]: e.target.value })}>
                    <option value="1">On</option><option value="0">Off</option></select>
                ) : i.kind === 'readonly' ? (
                  <div className="mt-1 text-slate-500 font-normal">{i.masked} — {i.help}</div>
                ) : (
                  <input type={i.kind === 'secret' ? 'password' : 'text'} autoComplete="off" className={inp + ' w-full mt-1 font-mono'} value={v}
                    placeholder={i.kind === 'secret' ? (i.masked || 'not set') : i.help} onChange={(e) => setVals({ ...vals, [i.key]: e.target.value })} />
                )}
              </label>
            );
          })}
        </div>
      ))}
      <div className="flex items-center gap-3"><button className={btn} disabled={!Object.keys(vals).length} onClick={save}>Save settings</button>{msg && <span className="text-[11px] text-blue-600">{msg}</span>}</div>
    </div>
  );
};

const StoreAdmin: React.FC = () => {
  const [q, setQ] = useState('');
  const [bots, setBots] = useState<any[]>([]);
  const [items, setItems] = useState<any[]>([]);
  const [msg, setMsg] = useState('');
  const [desc, setDesc] = useState<Record<string, string>>({});
  const loadItems = () => apiService.adminGet('store').then(setItems).catch((x) => setMsg(errMsg(x)));
  useEffect(() => { loadItems(); }, []);
  useEffect(() => { const t = setTimeout(() => apiService.adminGet(`bots?q=${encodeURIComponent(q)}`).then(setBots).catch(() => {}), 250); return () => clearTimeout(t); }, [q]);
  const add = async (b: any) => {
    try { await apiService.adminPost('store', { botId: b.id, category: b.category, description: desc[b.id] || '' }); setMsg(`${b.name} added to the Store`); loadItems(); setQ(q + ' '); setQ(q); } catch (x) { setMsg(errMsg(x)); }
  };
  const del = async (id: string) => { try { await apiService.adminDelete(`store/${id}`); loadItems(); } catch (x) { setMsg(errMsg(x)); } };
  return (
    <div className="space-y-4">
      {msg && <p className="text-[11px] text-blue-600">{msg}</p>}
      <div className={card + ' space-y-2'}>
        <div className="text-xs font-black">Add any bot to the Store</div>
        <input className={inp + ' w-full'} placeholder="Search bot name, @username or owner e-mail" value={q} onChange={(e) => setQ(e.target.value)} />
        {bots.map((b) => (
          <div key={b.id} className="flex flex-wrap items-center gap-2 text-xs border-t border-slate-100 dark:border-slate-800 pt-2">
            <div className="min-w-0 flex-1"><div className="font-bold truncate">{b.name} <span className="text-slate-400 font-normal">@{b.username}</span></div><div className="text-slate-500 truncate">{b.owner} · {b.commands} commands · {b.category}</div></div>
            <input className={inp + ' w-56'} placeholder="Short description (optional)" value={desc[b.id] || ''} onChange={(e) => setDesc({ ...desc, [b.id]: e.target.value })} />
            <button className={btn} onClick={() => add(b)}>{b.inStore ? 'Add again' : 'Add to Store'}</button>
          </div>
        ))}
      </div>
      <div className={card + ' space-y-2'}>
        <div className="text-xs font-black">In the Store now ({items.length})</div>
        {items.map((s) => (
          <div key={s.id} className="flex items-center gap-2 text-xs"><span className="flex-1 truncate font-bold">{s.name} <span className="text-slate-400 font-normal">{s.category} · {s.forks} clones · {s.author}</span></span>
            <button className="text-red-600 font-bold cursor-pointer" onClick={() => del(s.id)}>Remove</button></div>
        ))}
      </div>
    </div>
  );
};

const Tickets: React.FC = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [detail, setDetail] = useState<any | null>(null);
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [peerTyping, setPeerTyping] = useState(false);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const typingActiveRef = useRef(false);
  const [msg, setMsg] = useState('');
  const [filter, setFilter] = useState<'all' | 'open' | 'answered' | 'customer-reply' | 'closed'>('all');
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(() => {
    apiService.adminGet('tickets').then(setRows).catch((x) => setMsg(errMsg(x)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const openDetail = async (t: any) => {
    setSelected(t);
    setMsg('');
    try {
      const d = await apiService.adminGet(`tickets/${encodeURIComponent(t.id)}`);
      setDetail(d);
    } catch (x) {
      setMsg(errMsg(x));
      setDetail(null);
    }
  };

  // Live poll while a ticket is open
  useEffect(() => {
    if (!selected?.id) return;
    let stop = false;
    const tick = async () => {
      try {
        const d = await apiService.adminGet(`tickets/${encodeURIComponent(selected.id)}`);
        if (!stop) {
          setDetail(d);
          setPeerTyping(!!d?.userTyping);
        }
      } catch {}
    };
    const id = window.setInterval(tick, 2500);
    return () => { stop = true; window.clearInterval(id); };
  }, [selected?.id]);

  useEffect(() => {
    try { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); } catch {}
  }, [detail?.replies?.length, detail?.message]);

  const setStatus = async (status: string) => {
    if (!selected) return;
    setBusy(true);
    try {
      await apiService.adminPut(`tickets/${selected.id}`, { status });
      setMsg(status === 'closed' ? 'Ticket closed' : 'Status updated');
      await openDetail(selected);
      load();
    } catch (x) {
      setMsg(errMsg(x));
    } finally {
      setBusy(false);
    }
  };


  const notifyAdminTyping = (text: string) => {
    setReply(text);
    if (!selected?.id || (detail?.status || '').toLowerCase() === 'closed') return;
    const active = text.trim().length > 0;
    if (active) {
      if (!typingActiveRef.current) {
        typingActiveRef.current = true;
        apiService.adminSupportTyping(selected.id, true).catch(() => {});
      }
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      typingTimerRef.current = setTimeout(() => {
        typingActiveRef.current = false;
        apiService.adminSupportTyping(selected.id, false).catch(() => {});
      }, 2000);
    } else if (typingActiveRef.current) {
      typingActiveRef.current = false;
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      apiService.adminSupportTyping(selected.id, false).catch(() => {});
    }
  };

  const sendReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selected || !reply.trim() || sending) return;
    if ((detail?.status || '').toLowerCase() === 'closed') {
      setMsg('Ticket is closed. Reopen it to reply.');
      return;
    }
    setSending(true);
    setMsg('');
    try {
      await apiService.adminPost(`tickets/${selected.id}/reply`, { message: reply.trim() });
      setReply('');
      typingActiveRef.current = false;
      apiService.adminSupportTyping(selected.id, false).catch(() => {});
      await openDetail(selected);
      load();
    } catch (x) {
      setMsg(errMsg(x));
    } finally {
      setSending(false);
    }
  };

  const badge = (status: string) => {
    const s = (status || 'open').toLowerCase();
    const map: Record<string, string> = {
      open: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
      answered: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
      'customer-reply': 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
      closed: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
    };
    return map[s] || map.open;
  };

  const ticks = (r: any, mine: boolean) => {
    if (!mine) return null;
    const seen = !!r.seenAt;
    const delivered = !!r.deliveredAt || !!r.createdAt;
    return (
      <span className={`inline-flex ml-1 text-[10px] ${seen ? 'text-sky-400' : 'text-slate-400'}`} title={seen ? 'Seen' : delivered ? 'Delivered' : 'Sent'}>
        {seen || delivered ? '✓✓' : '✓'}
      </span>
    );
  };

  const filtered = rows.filter((r) => filter === 'all' || (r.status || 'open').toLowerCase() === filter);
  const closed = (detail?.status || '').toLowerCase() === 'closed';

  if (selected && detail) {
    const closed = (detail.status || '').toLowerCase() === 'closed';
    const bubbles = [
      {
        id: 'orig',
        message: detail.message || '',
        isStaff: false,
        authorName: detail.name || 'User',
        createdAt: detail.createdAt,
        deliveredAt: detail.createdAt,
        seenAt: detail.createdAt,
      },
      ...((detail.replies || []).map((r: any) => ({
        id: r.id,
        message: r.message,
        isStaff: !!r.isStaff,
        authorName: r.authorName,
        createdAt: r.createdAt,
        deliveredAt: r.deliveredAt || r.createdAt,
        seenAt: r.seenAt,
      }))),
    ];
    return (
      <div className="space-y-2 min-w-0 w-full">
        {msg && <p className="text-xs text-amber-700 dark:text-amber-300 font-semibold">{msg}</p>}
        <SupportChat
          perspective="admin"
          title={detail.subject || detail.category || 'Ticket'}
          subtitle={`${detail.name || ''} · ${detail.email || ''} · ${detail.department || detail.category || ''}`}
          status={detail.status || 'open'}
          userName={detail.name || 'User'}
          adminName="Admin"
          closed={closed}
          sending={sending}
          input={reply}
          onInput={notifyAdminTyping}
          peerTyping={peerTyping}
          peerTypingLabel={(detail?.name || "User") + " is typing"}
          onSend={sendReply}
          onBack={() => { setSelected(null); setDetail(null); }}
          closedHint="Ticket closed — neither Admin nor User can reply. Reopen to continue."
          messages={bubbles}
          headerRight={(
            <div className="flex gap-1">
              {!closed ? (
                <button type="button" disabled={busy} onClick={() => setStatus('closed')} className="px-2 py-1 rounded-lg text-[10px] font-bold bg-slate-200 dark:bg-slate-700 cursor-pointer">Close</button>
              ) : (
                <button type="button" disabled={busy} onClick={() => setStatus('open')} className="px-2 py-1 rounded-lg text-[10px] font-bold bg-blue-600 text-white cursor-pointer">Reopen</button>
              )}
            </div>
          )}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5 items-center">
        {(['all', 'open', 'answered', 'customer-reply', 'closed'] as const).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            className={`px-2.5 py-1 rounded-lg text-[10px] font-bold cursor-pointer ${
              filter === f ? 'bg-blue-600 text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
            }`}
          >
            {f} {f !== 'all' ? `(${rows.filter((r) => (r.status || 'open').toLowerCase() === f).length})` : `(${rows.length})`}
          </button>
        ))}
        <button type="button" onClick={load} className="ml-auto text-[10px] font-bold text-blue-600 cursor-pointer">
          Refresh
        </button>
      </div>
      {msg && <p className="text-xs text-red-500">{msg}</p>}
      {filtered.length === 0 && <p className="text-xs text-slate-500">No tickets.</p>}
      {filtered.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => openDetail(t)}
          className={card + ' text-xs space-y-1 w-full text-left cursor-pointer hover:border-blue-400 dark:hover:border-blue-600 transition'}
        >
          <div className="flex justify-between gap-2 flex-wrap">
            <b className="font-mono">{t.id}</b>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${badge(t.status)}`}>{t.status || 'open'}</span>
          </div>
          <div className="font-bold text-slate-900 dark:text-white">{t.subject || t.category}</div>
          <div className="text-slate-500">
            {t.name} · {t.email} · {t.department || t.category} · {t.priority}
          </div>
          <p className="line-clamp-2 text-slate-600 dark:text-slate-400">{t.message}</p>
          <div className="text-[10px] text-slate-400">{t.updatedAt || t.createdAt || ''}</div>
        </button>
      ))}
    </div>
  );
};


export const AdminView: React.FC = () => {
  const [tab, setTab] = useState<Tab>(() => { try { const v = localStorage.getItem('bm_admin_tab') as Tab; return TABS.includes(v) ? v : 'Server'; } catch { return 'Server'; } });
  const [lang, setLang] = useState<Lang>(() => { try { return localStorage.getItem('bm_admin_lang') === 'bn' ? 'bn' : 'en'; } catch { return 'en'; } });
  const pick = (x: Tab) => { setTab(x); try { localStorage.setItem('bm_admin_tab', x); } catch { /* ignore */ } };
  const flip = () => { const n: Lang = lang === 'en' ? 'bn' : 'en'; setLang(n); try { localStorage.setItem('bm_admin_lang', n); } catch { /* ignore */ } };
  return (
    <div className="space-y-4 max-w-6xl" data-testid="admin-panel">
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="relative overflow-hidden rounded-3xl p-5 text-white shadow-xl" style={{ background: 'linear-gradient(120deg,#312e81,#6d28d9,#be185d)', backgroundSize: '200% 200%' }}>
        <motion.div className="absolute -right-10 -top-10 w-48 h-48 rounded-full bg-white/10 blur-2xl" animate={{ scale: [1, 1.2, 1] }} transition={{ repeat: Infinity, duration: 6 }} />
        <div className="relative flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-white/15 backdrop-blur flex items-center justify-center"><Server className="w-6 h-6" /></div>
          <div className="flex-1"><h2 className="text-xl font-black">{t('title', lang)}</h2><p className="text-[11px] opacity-85">{lang === 'bn' ? 'সার্ভার, বট, ইউজার, ডাটাবেস ও সিকিউরিটি — সব এক জায়গায়' : 'Server, bots, users, database and security in one place'}</p></div>
          <button onClick={flip} className="px-3 py-1.5 rounded-xl bg-white/20 hover:bg-white/30 text-xs font-bold cursor-pointer flex items-center gap-1.5"><Languages className="w-4 h-4" />{lang === 'en' ? 'বাংলা' : 'English'}</button>
        </div>
      </motion.div>
      <div className="flex flex-wrap gap-1.5">
        {TABS.map((x) => { const Ic = TAB_ICON[x]; return (
          <button key={x} onClick={() => pick(x)} className={`px-3 py-2 rounded-2xl text-xs font-bold cursor-pointer flex items-center gap-1.5 transition-all ${tab === x ? `bg-gradient-to-r ${TAB_GRAD[x]} text-white shadow-md scale-[1.03]` : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'}`}>
            <Ic className="w-3.5 h-3.5" />{t(x.toLowerCase(), lang)}</button>); })}
      </div>
      <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
        {tab === 'Server' && <ServerPanel lang={lang} />}
        {tab === 'Fleet' && <FleetPanel lang={lang} />}
        {tab === 'Overview' && <Overview />}
        {tab === 'Users' && <Users />}
        {tab === 'Plans' && <Plans />}
        {tab === 'Database' && <DatabasePanel lang={lang} />}
        {tab === 'Logs' && <LogsPanel lang={lang} />}
        {tab === 'Security' && <SecurityPanel lang={lang} />}
        {tab === 'Store' && <StoreAdmin />}
        {tab === 'Settings' && <Settings />}
        {tab === 'Tickets' && <Tickets />}
      </motion.div>
    </div>
  );
};
