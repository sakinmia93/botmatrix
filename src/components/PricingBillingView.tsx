import React, { useEffect, useState } from 'react';
import { Check, Coins, Infinity as InfinityIcon, Send } from 'lucide-react';
import { apiService } from '../services/apiService';

interface Plan {
  id: string;
  name: string;
  priceUsd: number;
  points: number;
  limits: Record<string, number | boolean>;
  features: string[];
}

export const PricingBillingView: React.FC = () => {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [current, setCurrent] = useState('');
  const [points, setPoints] = useState(0);
  const [contactUrl, setContactUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    apiService.getPlans()
      .then(d => { if (alive) { setPlans(d.plans); setCurrent(d.current); setPoints(d.points); setContactUrl(d.contactUrl); } })
      .catch(e => alive && setError(e?.message || 'Could not load plans.'));
    return () => { alive = false; };
  }, []);

  const bots = (p: Plan) => (Number(p.limits.maxBots) < 0 ? 'Unlimited bots' : `${p.limits.maxBots} bots`);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-slate-900 dark:text-white">Plans &amp; Billing</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-1.5">
          <Coins className="w-4 h-4 text-amber-500" /> You have <strong className="text-slate-800 dark:text-slate-200">{points.toLocaleString()}</strong> points
        </p>
      </div>
      {error && <div className="p-3 rounded-xl bg-red-500/10 text-red-600 text-sm">{error}</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {plans.map(p => {
          const isCurrent = p.name === current;
          return (
            <div key={p.id} className={`flex flex-col rounded-2xl border p-5 bg-white dark:bg-slate-900 ${isCurrent ? 'border-blue-500 ring-2 ring-blue-500/20' : 'border-slate-200 dark:border-slate-800'}`}>
              <div className="flex items-center justify-between">
                <h2 className="text-base font-bold text-slate-900 dark:text-white">{p.name}</h2>
                {isCurrent && <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400">Current</span>}
              </div>
              <div className="mt-3 flex items-baseline gap-1">
                <span className="text-3xl font-extrabold text-slate-900 dark:text-white">${p.priceUsd}</span>
                <span className="text-xs text-slate-500">/ month</span>
              </div>
              <div className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-amber-600 dark:text-amber-400">
                <Coins className="w-4 h-4" /> {p.points.toLocaleString()} points
              </div>
              <ul className="mt-4 space-y-2 flex-1">
                <li className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                  {Number(p.limits.maxBots) < 0 ? <InfinityIcon className="w-4 h-4 mt-0.5 text-emerald-500 shrink-0" /> : <Check className="w-4 h-4 mt-0.5 text-emerald-500 shrink-0" />}
                  {bots(p)}
                </li>
                {p.features.filter(f => !/bots$/i.test(f) && !/points/i.test(f)).map(f => (
                  <li key={f} className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
                    <Check className="w-4 h-4 mt-0.5 text-emerald-500 shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              {(
                contactUrl ? (
                  <a href={contactUrl} target="_blank" rel="noopener noreferrer"
                    className="mt-5 inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold py-2.5 transition-colors">
                    <Send className="w-4 h-4" /> Contact Admin
                  </a>
                ) : (
                  <button disabled className="mt-5 rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-500 text-sm font-bold py-2.5 cursor-not-allowed">Contact Admin</button>
                )
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
