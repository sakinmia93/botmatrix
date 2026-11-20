import React, { useState, useEffect, useRef, Component, ErrorInfo, ReactNode } from 'react';
import { BotCommand, BotItem } from '../types';
import { ArrowLeft, Save, X, AlertTriangle } from 'lucide-react';

/** Catches render errors and shows them instead of white screen */
export class EditorErrorBoundary extends Component<
  { children: ReactNode; onBack?: () => void },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[EditorErrorBoundary]', error, info.componentStack);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="fixed inset-0 z-50 bg-slate-950 text-red-200 p-6 overflow-auto font-mono text-sm">
          <div className="max-w-3xl mx-auto space-y-4">
            <h1 className="text-lg font-bold text-red-400 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" /> Code Editor failed to open
            </h1>
            <pre className="whitespace-pre-wrap bg-red-950/50 border border-red-800 rounded-xl p-4 text-xs">
              {this.state.error.message}
              {'\n\n'}
              {this.state.error.stack}
            </pre>
            <button
              type="button"
              onClick={() => {
                this.setState({ error: null });
                this.props.onBack?.();
              }}
              className="px-4 py-2 rounded-xl bg-slate-800 text-white text-xs font-bold"
            >
              ← Back to Commands
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

interface SimpleCodeEditorProps {
  command: BotCommand;
  allCommands?: BotCommand[];
  bot?: BotItem;
  botName?: string;
  onBack?: () => void;
  onClose?: () => void;
  onSaveCommand?: (cmd: BotCommand, code: string) => void;
}

/** Reliable fullscreen code editor (textarea) — always opens, no white screen */
export const SimpleCodeEditor: React.FC<SimpleCodeEditorProps> = ({
  command,
  botName,
  onBack,
  onClose,
  onSaveCommand,
}) => {
  const [code, setCode] = useState(typeof command?.code === 'string' ? command.code : '');
  const [dirty, setDirty] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setCode(typeof command?.code === 'string' ? command.code : '');
    setDirty(false);
  }, [command?.id]);

  useEffect(() => {
    taRef.current?.focus();
  }, []);

  const handleSave = () => {
    if (!onSaveCommand) return;
    onSaveCommand({ ...command, code, updatedAt: 'Just now' }, code);
    setDirty(false);
    setToast(`Saved ${command.name}`);
    setTimeout(() => setToast(null), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#1e1e1e] text-slate-100">
      {toast && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-xl bg-emerald-900/90 text-emerald-100 text-xs font-semibold border border-emerald-700">
          {toast}
        </div>
      )}
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[#333] bg-[#252526] shrink-0">
        <button
          type="button"
          onClick={() => onBack?.() || onClose?.()}
          className="p-1.5 rounded-lg hover:bg-[#333] text-slate-300"
          title="Back"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <span className="text-xs font-mono font-bold text-blue-400">{command.name || '/command'}</span>
        <span className="text-[10px] text-slate-500 truncate">{botName || ''}</span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold ${
            dirty ? 'bg-blue-600 text-white hover:bg-blue-500' : 'bg-[#333] text-slate-500'
          }`}
        >
          <Save className="w-3.5 h-3.5" /> Save
        </button>
        <button
          type="button"
          onClick={() => onClose?.() || onBack?.()}
          className="p-1.5 rounded-lg hover:bg-[#333] text-slate-400"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      {/* Editor */}
      <textarea
        ref={taRef}
        value={code}
        onChange={(e) => {
          setCode(e.target.value);
          setDirty(true);
        }}
        spellCheck={false}
        className="flex-1 w-full p-4 font-mono text-sm leading-relaxed outline-none resize-none bg-[#1e1e1e] text-[#d4d4d4]"
        style={{ tabSize: 4 }}
        placeholder="# Write your bot command code here..."
      />
      <div className="px-3 py-1 border-t border-[#333] bg-[#252526] text-[10px] text-slate-500 font-mono shrink-0">
        {code.split('\n').length} lines · {code.length} chars · {dirty ? 'Unsaved' : 'Saved'}
      </div>
    </div>
  );
};
