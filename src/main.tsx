import {StrictMode, Component, type ReactNode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import { PublicReceipt } from './components/PublicReceipt';
import { clearBotMatrixStorage, sanitizeBootStorage } from './utils/safeStorage';
import './index.css';

// Repair corrupt localStorage before any React state reads it (prevents white screen)
try {
  sanitizeBootStorage();
} catch {
  try { clearBotMatrixStorage(); } catch {}
}

// Ensure window.fetch has both getter and setter in iframe environments
try {
  if (typeof window !== 'undefined') {
    const origFetch = window.fetch ? window.fetch.bind(window) : undefined;
    let currFetch = origFetch;
    try {
      Object.defineProperty(window, 'fetch', {
        get: () => currFetch || origFetch,
        set: (fn: typeof fetch) => {
          currFetch = fn;
        },
        configurable: true,
        enumerable: true,
      });
    } catch {
      // ignore
    }
  }
} catch {
  // ignore
}

class BootErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.error('[BOT MATRIX] boot error', error);
  }

  private reset = () => {
    // Soft recovery: only drop keys that commonly break boot; keep session if possible
    try {
      const userRaw = localStorage.getItem('telebot_user');
      if (userRaw) {
        try { JSON.parse(userRaw); } catch {
          localStorage.removeItem('telebot_user');
        }
      }
      localStorage.removeItem('telebot_active_tab');
      localStorage.removeItem('telebot_selected_bot');
    } catch {}
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
            fontFamily: 'system-ui, sans-serif',
            background: '#0f172a',
            color: '#e2e8f0',
          }}
        >
          <div style={{ maxWidth: 420, width: '100%', textAlign: 'center' }}>
            <h1 style={{ fontSize: 18, fontWeight: 800, marginBottom: 8 }}>BOT MATRIX failed to load</h1>
            <p style={{ fontSize: 13, color: '#94a3b8', marginBottom: 16, lineHeight: 1.5 }}>
              Something went wrong while loading. You can reload; the app will try to recover automatically.
            </p>
            <pre
              style={{
                textAlign: 'left',
                fontSize: 11,
                background: '#1e293b',
                padding: 12,
                borderRadius: 12,
                overflow: 'auto',
                maxHeight: 120,
                marginBottom: 16,
                color: '#f87171',
              }}
            >
              {String(this.state.error?.message || this.state.error)}
            </pre>
            <button
              type="button"
              onClick={this.reset}
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: 12,
                border: 'none',
                background: '#2563eb',
                color: '#fff',
                fontWeight: 700,
                fontSize: 14,
                cursor: 'pointer',
              }}
            >
              Reload app
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const receiptMatch = window.location.pathname.match(/^\/receipt\/([^/]+)$/);
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BootErrorBoundary>
      {receiptMatch ? <PublicReceipt code={decodeURIComponent(receiptMatch[1])} /> : <App />}
    </BootErrorBoundary>
  </StrictMode>,
);
