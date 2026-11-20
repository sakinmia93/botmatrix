import React, { useEffect, useRef, useState } from 'react';

declare global { interface Window { turnstile?: any; __bmTsLoading?: Promise<void>; } }

export interface PublicConfig { turnstile: { enabled: boolean; siteKey: string }; otpRequired: boolean }

let cfgPromise: Promise<PublicConfig> | null = null;
export function loadPublicConfig(): Promise<PublicConfig> {
  if (!cfgPromise) {
    cfgPromise = fetch('/api/config').then((r) => r.json()).catch(() => ({ turnstile: { enabled: false, siteKey: '' }, otpRequired: true }));
  }
  return cfgPromise;
}

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (!window.__bmTsLoading) {
    window.__bmTsLoading = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error('Could not load human verification'));
      document.head.appendChild(s);
    });
  }
  return window.__bmTsLoading;
}

/** Cloudflare Turnstile widget. Renders nothing at all when the server has it switched off. */
export const TurnstileBox: React.FC<{ siteKey: string; resetKey: number; onToken: (t: string) => void }> = ({ siteKey, resetKey, onToken }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let id: any = null;
    let dead = false;
    onToken('');
    loadScript().then(() => {
      if (dead || !ref.current || !window.turnstile) return;
      id = window.turnstile.render(ref.current, {
        sitekey: siteKey,
        appearance: 'interaction-only',
        callback: (t: string) => onToken(t),
        'expired-callback': () => onToken(''),
        'error-callback': () => { onToken(''); setErr('Human verification failed to load. Reload the page.'); },
      });
    }).catch((e) => setErr(e.message));
    return () => { dead = true; try { if (id !== null) window.turnstile?.remove(id); } catch {} };
  }, [siteKey, resetKey]);
  return (<><div ref={ref} className="flex justify-center" />{err && <p className="text-xs text-red-500 text-center">{err}</p>}</>);
};
