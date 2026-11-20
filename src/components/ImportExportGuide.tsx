import React, { useEffect } from 'react';
import { X, HelpCircle } from 'lucide-react';
import { createPortal } from 'react-dom';

const Code: React.FC<{ children: string }> = ({ children }) => (
  <pre className="mt-1 p-3 rounded-xl bg-slate-900 text-slate-100 text-[11px] leading-relaxed overflow-x-auto font-mono whitespace-pre">{children}</pre>
);
const H: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h4 className="text-sm font-bold text-slate-900 dark:text-white mt-5 mb-1">{children}</h4>
);

export const ImportExportGuide: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  // Lock background page scroll while guide is open
  useEffect(() => {
    const prev = document.body.style.overflow;
    const prevHtml = document.documentElement.style.overflow;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      document.documentElement.style.overflow = prevHtml;
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  const node = (
    <div
      className="fixed inset-0 z-[300] bg-slate-950/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Import and export guide"
      onClick={onClose}
      onWheel={(e) => e.stopPropagation()}
      onTouchMove={(e) => e.stopPropagation()}
    >
      <div
        className="w-full sm:max-w-3xl h-[92dvh] sm:h-auto sm:max-h-[88vh] flex flex-col rounded-t-3xl sm:rounded-3xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onWheel={(e) => e.stopPropagation()}
        onTouchMove={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 p-4 sm:p-6 pb-2 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <HelpCircle className="w-5 h-5 text-blue-600 shrink-0" />
            <div className="min-w-0">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white truncate">Import &amp; export guide</h3>
              <p className="text-xs text-slate-500 mt-0.5">Which file works where. Bot tokens are never exported.</p>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close guide" className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 sm:px-6 pb-8 pt-2" style={{ WebkitOverflowScrolling: 'touch' }}>
          <H>1. Users — import</H>
          <p className="text-xs text-slate-600 dark:text-slate-300">Files with Telegram user IDs. Each ID is verified through Telegram (about 10 per second), so only users who started your bot are added. Existing users are untouched.</p>
          <Code>{`TXT  — any separators:
123456789
987654321, 555000111

CSV  — header optional (id / telegram_id / user_id / chat_id column is used):
telegram_id,name
123456789,Siam

JSON — a list of IDs, or objects, or {"users": [...]}:
[123456789, "987654321", {"id": 555000111}]`}</Code>

          <H>2. Users — export</H>
          <p className="text-xs text-slate-600 dark:text-slate-300">Choose JSON, CSV or TXT (IDs only), which users (all / active / blocked / active 7 days / inactive 30+ days) and the columns: ID, name, username, blocked, registration date, last active, last message, message count, language. A file exported here can be imported again.</p>

          <H>3. Environment variables</H>
          <p className="text-xs text-slate-600 dark:text-slate-300">Import and export from the Environment Variables box. Accepted: .env (KEY=value lines), JSON and YAML. Existing keys are updated, new keys are added.</p>

          <H>4. Bot — full package</H>
          <p className="text-xs text-slate-600 dark:text-slate-300">Export commands, env, settings, optional bot database and user IDs as JSON, YAML or TXT. Import shows a preview before applying. Tick “Replace” only when you want to remove commands/vars/data that are not in the file. The bot token is never included.</p>

          <H>5. Tips</H>
          <ul className="text-xs text-slate-600 dark:text-slate-300 list-disc pl-4 space-y-1">
            <li>Untick “Include variable values” before sharing an export.</li>
            <li>Large user exports show live progress and a Download button when ready.</li>
            <li>Commands with code errors are skipped on import and listed.</li>
          </ul>
          <div className="h-6" />
        </div>
      </div>
    </div>
  );

  return typeof document !== 'undefined' ? createPortal(node, document.body) : node;
};

export default ImportExportGuide;
