import React, { useState, useEffect, useRef, useCallback } from 'react';
import ace from 'ace-builds';

// Ace modes, themes, and extensions
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-javascript';
import 'ace-builds/src-noconflict/mode-html';
import 'ace-builds/src-noconflict/mode-css';
import 'ace-builds/src-noconflict/mode-json';
import 'ace-builds/src-noconflict/theme-tomorrow_night';
import 'ace-builds/src-noconflict/theme-chrome';
import 'ace-builds/src-noconflict/ext-language_tools';
import 'ace-builds/src-noconflict/ext-searchbox';

// Suppress Ace basePath inference warning from console.error
if (typeof console !== 'undefined' && console.error) {
  const origConsoleError = console.error;
  console.error = function (...args: any[]) {
    if (
      args.length > 0 &&
      typeof args[0] === 'string' &&
      args[0].indexOf('Unable to infer path to ace') !== -1
    ) {
      return;
    }
    return origConsoleError.apply(console, args);
  };
}

// Configure Ace base paths to empty strings to prevent external CDN network requests
ace.config.set('basePath', '');
ace.config.set('modePath', '');
ace.config.set('themePath', '');
(ace.config as any).set('workerPath', '');
(ace.config as any).set('useWorker', false);

// Prevent Ace from ever attempting to spawn Web Workers in browser sandbox
try {
  (ace.EditSession.prototype as any).$startWorker = function () {
    this.$worker = null;
  };
} catch (_) {}


import {
  ArrowLeft,
  Play,
  Wand2,
  Save,
  Check,
  RotateCcw,
  RotateCw,
  Search,
  X,
  Copy,
  Download,
  Upload,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  MoreVertical,
  Code2,
  FileCode,
  FileText,
  Clipboard,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  WrapText,
  Type,
  Sun,
  Moon,
  Plus,
  Minus,
  FolderPlus,
  Bug,
  Pencil,
  Folder,
  Shield,
  Pin,
  Columns2,
  RefreshCw,
  HelpCircle,
} from 'lucide-react';
import { BotCommand } from '../types';
import { apiService } from '../services/apiService';
import { createRealCompleter, validateRemote } from '../utils/editorService';
import type { SyntaxCheckResult } from '../utils/pythonSyntaxChecker';
import { SyntaxCheckPanel } from './SyntaxCheckPanel';
import { PasteCodeModal } from './PasteCodeModal';

const ERRORS_TAB_ID = '__errors__';

interface OpenTabItem {
  id: string;
  name: string;
  code: string;
  commandRef?: BotCommand;
  isModified?: boolean;
}

// ---- unsaved-work drafts (survive refresh, crash, power loss, lost network) ----
const draftKey = (scope: string, id: string) => `bm_draft_${scope}_${id}`;
const readDraft = (scope: string, id: string): { code: string; ts: number; accepted?: boolean; undo?: any } | null => {
  try {
    const raw = localStorage.getItem(draftKey(scope, id));
    if (!raw) return null;
    const d = JSON.parse(raw);
    return d && typeof d.code === 'string' ? d : null;
  } catch { return null; }
};
// accepted = the user already answered "Yes, continue" for this draft, so it is restored silently from now on.
// undo = the undo/redo history, so Undo and Redo still work after the device was off.
const writeDraft = (scope: string, id: string, code: string, undo?: any, accepted?: boolean) => {
  try {
    const prev = readDraft(scope, id);
    const rec: any = { code, ts: Date.now(), accepted: accepted ?? prev?.accepted ?? false };
    if (undo) { const s = JSON.stringify(undo); if (s.length < 600_000) rec.undo = undo; }
    localStorage.setItem(draftKey(scope, id), JSON.stringify(rec));
  } catch {}
};
const sessionDraft = (scope: string, id: string, sess: any, accepted?: boolean) => {
  let undo: any;
  try { undo = sess.getUndoManager().toJSON(); } catch {}
  writeDraft(scope, id, sess.getValue(), undo, accepted);
};
const clearDraft = (scope: string, id: string) => {
  try { localStorage.removeItem(draftKey(scope, id)); } catch {}
};

interface TelebotIDEProps {
  initialCommand?: BotCommand | null;
  command?: BotCommand | null;
  allCommands?: BotCommand[];
  botName?: string;
  botUsername?: string;
  bot?: { id?: string; name?: string; username?: string; commands?: BotCommand[] };
  onBack?: () => void;
  onClose?: () => void;
  onSaveCommand?: (
    commandOrId: BotCommand | string,
    updatedCode?: string,
    metadata?: Partial<BotCommand>
  ) => void | Promise<{ ok: boolean; error?: string; errors?: { line: number; message: string }[] } | void>;
  onSelectOtherCommand?: (command: BotCommand) => void;
  onRunSimulation?: (cmd: BotCommand) => void;
  onCreateCommand?: (command: BotCommand) => void;
  /** Jump editor to this line when opening (from Errors tab). */
  initialJumpLine?: number | null;
}

// File badge helper: Python commands
const getFileBadge = (_name: string, _code?: string): string => {
  return 'BMP';
};

// Ace Mode detector: strictly Python
const getAceMode = (_name: string, _code?: string): string => {
  return 'python';
};

export const TelebotIDE: React.FC<TelebotIDEProps> = ({
  initialCommand,
  command,
  allCommands = [],
  botName,
  bot,
  onBack,
  onClose,
  onSaveCommand,
  onCreateCommand,
  onRequestEditCommand,
  initialJumpLine = null,
}) => {
  // Helper to reliably resolve full code for any command from props or allCommands
  const getCommandCode = useCallback(
    (cmd?: Partial<BotCommand> | null): string => {
      if (!cmd) return '';
      if (typeof cmd.code === 'string' && cmd.code.trim().length > 0) {
        return cmd.code;
      }
      const matched = allCommands.find((c) => c.id === cmd.id || c.name === cmd.name);
      if (matched && typeof matched.code === 'string' && matched.code.trim().length > 0) {
        return matched.code;
      }
      return '';
    },
    [allCommands]
  );

  const resolvedCmd = initialCommand || command || allCommands[0] || {
    id: 'cmd-start',
    name: '/start',
    code: '',
  };

  const resolvedBotName = botName || bot?.name || 'Bot';
  const initialResolvedCode = getCommandCode(resolvedCmd);

  // Track the saved baseline code for each tab so undo back to original disables the Save button
  const savedCodeMapRef = useRef<Map<string, string>>(new Map([[resolvedCmd.id, initialResolvedCode]]));

  // Open tabs state
  const [openTabs, setOpenTabs] = useState<OpenTabItem[]>([
    {
      id: resolvedCmd.id,
      name: resolvedCmd.name,
      code: initialResolvedCode,
      commandRef: { ...resolvedCmd, code: initialResolvedCode },
      isModified: false,
    },
  ]);
  const draftScope = String(bot?.username || botName || 'bot').replace(/[^A-Za-z0-9_]/g, '');
  const draftScopeRef = useRef(draftScope);
  draftScopeRef.current = draftScope;
  const draftTimers = useRef<Map<string, any>>(new Map());
  const [pendingDraft, setPendingDraft] = useState<{ tabId: string; code: string; ts: number } | null>(null);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);
  const [activeTabId, setActiveTabId] = useState<string>(resolvedCmd.id);
  const activeTabIdRef = useRef<string>(resolvedCmd.id);

  // Per-Tab Isolated Ace EditSessions to guarantee 100% separate documents, undo/redo stacks, and cursor state
  const sessionsRef = useRef<Map<string, ace.Ace.EditSession>>(new Map());
  const prevActiveTabIdRef = useRef<string>(resolvedCmd.id);
  const openTabsRef = useRef(openTabs);
  useEffect(() => {
    openTabsRef.current = openTabs;
  }, [openTabs]);

  // Can undo / can redo / can save states
  const [canUndo, setCanUndo] = useState<boolean>(false);
  const [canRedo, setCanRedo] = useState<boolean>(false);
  const [canSave, setCanSave] = useState<boolean>(false);

  // Syntax Checker modal & state
  const [showSyntaxChecker, setShowSyntaxChecker] = useState<boolean>(false);
  const [syntaxResult, setSyntaxResult] = useState<SyntaxCheckResult>({
    isValid: true,
    errors: [],
    warnings: [],
  });

  // Direct Paste Code modal
  const [showPasteModal, setShowPasteModal] = useState<boolean>(false);

  // Plus (+) new tab dropdown
  const [showNewTabSelector, setShowNewTabSelector] = useState(false);
  const [newTabSearch, setNewTabSearch] = useState('');
  const newTabSearchInputRef = useRef<HTMLInputElement | null>(null);
  const newTabDropdownRef = useRef<HTMLDivElement | null>(null);

  // Edit command details (tab pencil)
  const [editDetailsOpen, setEditDetailsOpen] = useState(false);
  const [editDetailsTabId, setEditDetailsTabId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editFolder, setEditFolder] = useState('All');
  const [editAliases, setEditAliases] = useState('');
  const [editAdminOnly, setEditAdminOnly] = useState(false);
  const [editPinned, setEditPinned] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [quickBarAboveKeyboard, setQuickBarAboveKeyboard] = useState(true);
  const [keyboardLift, setKeyboardLift] = useState(0);
  const [createCmdName, setCreateCmdName] = useState('');

  // Errors tab (same data as Bot Studio Errors tab)
  const [liveErrors, setLiveErrors] = useState<any[] | null>(null);
  const [openErrId, setOpenErrId] = useState<string | null>(null);
  const [confirmClearErrors, setConfirmClearErrors] = useState(false);
  const [errorTimeFormat, setErrorTimeFormat] = useState<'local' | 'utc' | 'relative'>('local');
  const formatErrorTime = (raw: any) => {
    if (!raw) return '';
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return String(raw);
    if (errorTimeFormat === 'utc') return d.toISOString().replace('T', ' ').replace('Z', ' UTC');
    if (errorTimeFormat === 'relative') {
      const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
      if (sec < 60) return sec + 's ago';
      if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
      if (sec < 86400) return Math.floor(sec / 3600) + 'h ago';
      return Math.floor(sec / 86400) + 'd ago';
    }
    return d.toLocaleString();
  };

  // Mobile overflow "More Tools" menu
  const [showMobileMore, setShowMobileMore] = useState(false);
  const mobileMoreRef = useRef<HTMLDivElement | null>(null);

  // Hidden File input ref for importing .txt files
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Editor states
  const DEFAULT_FONT_SIZE = 13;
  const [fontSize, setFontSize] = useState<number>(DEFAULT_FONT_SIZE);
  const [ideTheme, setIdeTheme] = useState<'dark' | 'light'>('dark');
  const [isWordWrap, setIsWordWrap] = useState<boolean>(true);
  const [cursorPos, setCursorPos] = useState<{ line: number; col: number }>({ line: 1, col: 1 });
  const [editorLineCount, setEditorLineCount] = useState<number>(1);

  // New Command Creation states inside the (+) selector
  const [newCmdNameInput, setNewCmdNameInput] = useState('');
  const [newCmdFolderInput, setNewCmdFolderInput] = useState('All');

  // Font size adjust logic: 1-10 step 2 (2, 4, 6, 8, 10), then 11-30 step 1
  const handleIncreaseFontSize = () => {
    setFontSize((prev) => {
      if (prev >= 30) return 30;
      if (prev < 10) return Math.min(10, prev + 2);
      return Math.min(30, prev + 1);
    });
  };

  const handleDecreaseFontSize = () => {
    setFontSize((prev) => {
      if (prev <= 2) return 2;
      if (prev <= 10) return Math.max(2, prev - 2);
      return Math.max(2, prev - 1);
    });
  };

  // Find & Replace state
  const [showSearch, setShowSearch] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [replaceQuery, setReplaceQuery] = useState('');
  const [matchCase, setMatchCase] = useState(false);
  const [matchWholeWord, setMatchWholeWord] = useState(false);
  const [useRegex, setUseRegex] = useState(false);
  const [matchCount, setMatchCount] = useState<number>(0);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  // Notifications / feedback
  const [feedbackToast, setFeedbackToast] = useState<{ message: string; type: 'success' | 'info' | 'error' | 'warning' } | null>(null);
  const showNotification = (message: string, type: 'success' | 'info' | 'error' | 'warning' = 'success', ms = 2400) => {
    setFeedbackToast({ message, type });
    setTimeout(() => setFeedbackToast(null), ms);
  };

  // Ace Editor instance ref & container ref
  const aceEditorRef = useRef<ace.Ace.Editor | null>(null);
  const editorContainerRef = useRef<HTMLDivElement | null>(null);
  const tabsScrollContainerRef = useRef<HTMLDivElement | null>(null);

  const activeTab = openTabs.find((t) => t.id === activeTabId) || openTabs[0];
  const activeMode = getAceMode(activeTab?.name || '', activeTab?.code || '');

  // Keep ref in sync
  useEffect(() => {
    activeTabIdRef.current = activeTabId;
    // Auto-scroll active tab into view for smooth PC/mobile navigation
    if (tabsScrollContainerRef.current) {
      const activeEl = tabsScrollContainerRef.current.querySelector(
        `[data-tab-id="${activeTabId}"]`
      ) as HTMLElement | null;
      if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', inline: 'nearest', block: 'nearest' });
      }
    }
  }, [activeTabId]);

  // Lock body scroll on mount
  useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  // Helper to get or create an isolated EditSession for a tab
  const getOrCreateSession = useCallback(
    (tab: OpenTabItem, initialWrap = isWordWrap): ace.Ace.EditSession => {
      let session = sessionsRef.current.get(tab.id);
      const originalCode = savedCodeMapRef.current.get(tab.id) ?? tab.code ?? '';

      if (!session) {
        const mode = getAceMode(tab.name);
        const safeCode = typeof tab.code === 'string' && tab.code.length > 0 ? tab.code : originalCode;
        if (!savedCodeMapRef.current.has(tab.id)) {
          savedCodeMapRef.current.set(tab.id, safeCode);
        }

        session = new ace.EditSession(safeCode);
        session.setUseWorker(false);
        session.setMode(`ace/mode/${mode}`);
        session.setUndoManager(new ace.UndoManager());
        session.setTabSize(4);
        session.setUseSoftTabs(true);
        session.setUseWrapMode(initialWrap);

        // Listen for changes strictly within this session
        session.on('change', () => {
          if (!session) return;
          const currentVal = session.getValue();
          const baseSaved = savedCodeMapRef.current.get(tab.id) ?? '';
          const isDirty = currentVal !== baseSaved;
          const um = session.getUndoManager();

          setCanUndo(um.hasUndo());
          setCanRedo(um.hasRedo());
          setCanSave(isDirty);
          setEditorLineCount(session.getLength());

          clearTimeout(draftTimers.current.get(tab.id));
          draftTimers.current.set(tab.id, setTimeout(() => {
            if (session && session.getValue() !== (savedCodeMapRef.current.get(tab.id) ?? '')) sessionDraft(draftScopeRef.current, tab.id, session);
            else clearDraft(draftScopeRef.current, tab.id);
          }, 300));

          setOpenTabs((prev) => {
            const currentTabItem = prev.find((t) => t.id === tab.id);
            if (!currentTabItem || currentTabItem.isModified === isDirty) return prev;
            return prev.map((t) => (t.id === tab.id ? { ...t, isModified: isDirty } : t));
          });
        });

        sessionsRef.current.set(tab.id, session);
        const dr = readDraft(draftScopeRef.current, tab.id);
        if (dr && dr.code !== safeCode) {
          // always ask again while the draft differs from the saved code (device may have died after a previous 'Yes')
          setTimeout(() => setPendingDraft({ tabId: tab.id, code: dr.code, ts: dr.ts }), 0);
        }
      } else {
        // If session exists but was empty and tab now has code, update it
        if ((!session.getValue() || session.getValue().trim().length === 0) && tab.code) {
          session.setValue(tab.code);
          if (!savedCodeMapRef.current.has(tab.id)) {
            savedCodeMapRef.current.set(tab.id, tab.code);
          }
        }
      }
      return session;
    },
    [isWordWrap]
  );

  // Mount native Ace Editor instance once and attach current tab session
  useEffect(() => {
    if (!editorContainerRef.current) return;

    const editor = ace.edit(editorContainerRef.current);
    editor.setTheme(ideTheme === 'dark' ? 'ace/theme/tomorrow_night' : 'ace/theme/chrome');
    editor.setFontSize(fontSize);
    editor.setShowPrintMargin(false);
    editor.renderer.setShowGutter(true);
    editor.setHighlightActiveLine(true);
    editor.setOptions({
      enableBasicAutocompletion: true,
      enableLiveAutocompletion: true,
      enableSnippets: true,
      showLineNumbers: true,
      useWorker: false,
      behavioursEnabled: true,
      wrapBehavioursEnabled: true,
      autoScrollEditorIntoView: true,
    });

    // Suggestions come only from the real runtime catalog (no static / generic word lists)
    (editor as any).completers = [createRealCompleter()];

    aceEditorRef.current = editor;

    // Attach active tab's session
    const currentTab =
      openTabsRef.current.find((t) => t.id === activeTabIdRef.current) || openTabsRef.current[0];
    if (currentTab) {
      const session = getOrCreateSession(currentTab, isWordWrap);
      editor.setSession(session);
      const um = session.getUndoManager();
      setCanUndo(um.hasUndo());
      setCanRedo(um.hasRedo());
      setCanSave(Boolean(currentTab.isModified));
      setEditorLineCount(session.getLength());
    }

    editor.on('changeSelection', () => {
      const pos = editor.getCursorPosition();
      setCursorPos({ line: pos.row + 1, col: pos.column + 1 });
    });

    // Guarantee instant Ace viewport layout, rendering, and focus upon opening editor
    const triggerInitialLayout = () => {
      if (editor && editor.renderer) {
        editor.resize(true);
        editor.renderer.updateFull();
        editor.focus();
      }
    };
    triggerInitialLayout();
    const rafId = requestAnimationFrame(triggerInitialLayout);
    const timerId = setTimeout(triggerInitialLayout, 60);

    const ro = new ResizeObserver(() => {
      editor.resize();
    });
    ro.observe(editorContainerRef.current);

    return () => {
      cancelAnimationFrame(rafId);
      clearTimeout(timerId);
      ro.disconnect();
      try {
        sessionsRef.current.forEach((sess) => {
          try {
            (sess as any)?.bgTokenizer?.stop?.();
          } catch (_) {}
        });
        editor.destroy();
      } catch (_) {}
      // destroy() also destroys every session it touched; never reuse them (React StrictMode remounts this effect)
      sessionsRef.current.clear();
      aceEditorRef.current = null;
    };
  }, []);

  // Sync font size with Ace
  useEffect(() => {
    if (aceEditorRef.current) {
      aceEditorRef.current.setFontSize(fontSize);
    }
  }, [fontSize]);

  // Sync theme with Ace
  useEffect(() => {
    if (aceEditorRef.current) {
      aceEditorRef.current.setTheme(
        ideTheme === 'dark' ? 'ace/theme/tomorrow_night' : 'ace/theme/chrome'
      );
    }
  }, [ideTheme]);

  // Switch session cleanly when active tab changes, isolating undo/redo stacks
  useEffect(() => {
    if (!aceEditorRef.current) return;
    if (activeTabId === ERRORS_TAB_ID) return; // Errors tab has no Ace session
    const editor = aceEditorRef.current;
    const targetTab = openTabsRef.current.find((t) => t.id === activeTabId) || openTabsRef.current[0];
    if (!targetTab || targetTab.id === ERRORS_TAB_ID) return;

    activeTabIdRef.current = targetTab.id;
    const session = getOrCreateSession(targetTab, isWordWrap);
    editor.setSession(session);
    session.setUseWrapMode(isWordWrap);

    // If session has no code but targetTab has code, ensure it is set
    if ((!session.getValue() || session.getValue().trim().length === 0) && targetTab.code) {
      session.setValue(targetTab.code);
    }

    // Update undo/redo and save flags strictly for this tab based on baseline comparison
    const um = session.getUndoManager();
    const currentVal = session.getValue();
    const baseSaved = savedCodeMapRef.current.get(targetTab.id) ?? targetTab.code ?? '';
    const isDirty = currentVal !== baseSaved;

    setCanUndo(um.hasUndo());
    setCanRedo(um.hasRedo());
    setCanSave(isDirty);
    setEditorLineCount(session.getLength());

    editor.focus();
  }, [activeTabId, getOrCreateSession, isWordWrap]);

  // Sync word wrap setting with Ace session
  useEffect(() => {
    if (aceEditorRef.current) {
      const session = aceEditorRef.current.getSession();
      if (session) {
        session.setUseWrapMode(isWordWrap);
      }
    }
  }, [isWordWrap]);

  // Click outside to close dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        newTabDropdownRef.current &&
        !newTabDropdownRef.current.contains(e.target as Node)
      ) {
        setShowNewTabSelector(false);
      }
      if (
        mobileMoreRef.current &&
        !mobileMoreRef.current.contains(e.target as Node)
      ) {
        setShowMobileMore(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Sync external command data into tabs — do NOT force-switch active tab (Errors / user selection stays)
  useEffect(() => {
    const cmd = initialCommand || command;
    if (!cmd) return;
    const codeToLoad = getCommandCode(cmd);
    if (!savedCodeMapRef.current.has(cmd.id)) {
      savedCodeMapRef.current.set(cmd.id, codeToLoad);
    }

    setOpenTabs((prev) => {
      const found = prev.find((t) => t.id === cmd.id);
      if (found) {
        if (!found.code && codeToLoad) {
          return prev.map((t) =>
            t.id === cmd.id ? { ...t, code: codeToLoad, commandRef: cmd, name: cmd.name || t.name } : t
          );
        }
        return prev.map((t) =>
          t.id === cmd.id ? { ...t, commandRef: { ...t.commandRef, ...cmd, code: t.code }, name: cmd.name || t.name } : t
        );
      }
      // Do not auto-add or switch while user is on Errors
      if (activeTabIdRef.current === ERRORS_TAB_ID) return prev;
      return [
        ...prev,
        {
          id: cmd.id,
          name: cmd.name,
          code: codeToLoad,
          commandRef: cmd,
          isModified: false,
        },
      ];
    });

    const session = sessionsRef.current.get(cmd.id);
    if (session && (!session.getValue() || session.getValue().trim().length === 0) && codeToLoad) {
      session.setValue(codeToLoad);
    }
    // Never call setActiveTabId here — keeps Errors / newly created tabs selected
  }, [initialCommand?.id, command?.id, getCommandCode]);

  // Calculate live search matches
  const calculateMatches = useCallback(
    (query: string, code: string) => {
      if (!query || !code) {
        setMatchCount(0);
        return;
      }
      try {
        let flags = 'g';
        if (!matchCase) flags += 'i';
        let pattern = query;
        if (!useRegex) {
          pattern = pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        }
        if (matchWholeWord) {
          pattern = `\\b${pattern}\\b`;
        }
        const regex = new RegExp(pattern, flags);
        const matches = code.match(regex);
        setMatchCount(matches ? matches.length : 0);
      } catch {
        setMatchCount(0);
      }
    },
    [matchCase, matchWholeWord, useRegex]
  );

  useEffect(() => {
    if (showSearch && searchQuery && activeTab?.code) {
      calculateMatches(searchQuery, activeTab.code);
    } else {
      setMatchCount(0);
    }
  }, [showSearch, searchQuery, activeTab?.code, calculateMatches]);

  // Find next/prev using Ace search engine
  const handleFind = useCallback(
    (backwards = false) => {
      if (!aceEditorRef.current || !searchQuery) return;
      aceEditorRef.current.find(searchQuery, {
        backwards,
        wrap: true,
        caseSensitive: matchCase,
        wholeWord: matchWholeWord,
        regExp: useRegex,
      });
      if (activeTab?.code) {
        calculateMatches(searchQuery, activeTab.code);
      }
    },
    [searchQuery, matchCase, matchWholeWord, useRegex, activeTab?.code, calculateMatches]
  );

  // Replace current match
  const handleReplace = () => {
    if (!aceEditorRef.current || !searchQuery) return;
    aceEditorRef.current.replace(replaceQuery);
    handleFind(false);
  };

  // Replace all matches
  const handleReplaceAll = () => {
    if (!aceEditorRef.current || !searchQuery) return;
    aceEditorRef.current.replaceAll(replaceQuery, {
      caseSensitive: matchCase,
      wholeWord: matchWholeWord,
      regExp: useRegex,
    });
    if (activeTab?.code) {
      calculateMatches(searchQuery, activeTab.code);
    }
    showNotification('All occurrences replaced');
  };

  // Format code on the server (real Python structure, checked to keep the program identical)
  const handleFormatCode = useCallback(async () => {
    if (!activeTab || !aceEditorRef.current) return;
    const currentCode = aceEditorRef.current.getValue();
    try {
      const r = await apiService.formatCode(currentCode);
      if (!r.ok) { showNotification(r.error || 'Fix the syntax error first', 'info'); return; }
      if (!r.changed || r.code === currentCode) { showNotification('Code is already clean', 'info'); return; }
      const session = aceEditorRef.current!.getSession();
      const cursor = aceEditorRef.current!.getCursorPosition();
      // replace through the document (not setValue) so Undo / Redo keep working after Format
      const lastRow = session.getLength() - 1;
      session.replace({ start: { row: 0, column: 0 }, end: { row: lastRow, column: session.getLine(lastRow).length } } as any, r.code || '');
      aceEditorRef.current!.moveCursorToPosition(cursor);
      setCanUndo(session.getUndoManager().hasUndo());
      setCanRedo(session.getUndoManager().hasRedo());
      showNotification('Code formatted', 'success');
    } catch {
      showNotification('Could not format right now', 'info');
    }
  }, [activeTab]);

  // Run the command for real (dry run: Telegram calls are listed, nothing is sent)
  const [runOpen, setRunOpen] = useState(false);
  const [runBusy, setRunBusy] = useState(false);
  const [runText, setRunText] = useState('');
  const [runUpdateType, setRunUpdateType] = useState('message');
  const [runCallbackData, setRunCallbackData] = useState('');
  const [runResult, setRunResult] = useState<any>(null);
  const handleRun = useCallback(async () => {
    if (!activeTab || !aceEditorRef.current) return;
    if (!bot?.id) { showNotification('Open this command from a bot to run it', 'info'); return; }
    setRunOpen(true);
    setRunBusy(true);
    try {
      const code = aceEditorRef.current.getValue();
      const text = runText.trim() || (activeTab.name.startsWith('/') ? activeTab.name : '');
      const payload: any = {
        name: activeTab.name,
        code,
        text,
        update_type: runUpdateType || 'message',
      };
      if (runCallbackData.trim() || runUpdateType === 'callback_query') {
        payload.callbackData = runCallbackData.trim() || text || 'btn';
        payload.update_type = 'callback_query';
      }
      setRunResult(await apiService.testCommand(bot.id, payload));
    } catch (e: any) {
      setRunResult({ ok: false, error: e?.message || 'The test could not run.', calls: [], durationMs: 0 });
    } finally {
      setRunBusy(false);
    }
  }, [activeTab, bot?.id, runText, runUpdateType, runCallbackData]);

  // Global keyboard shortcuts (Ctrl+S, Ctrl+F, Ctrl+H, Alt+Shift+F, Esc)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        handleSave();
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        setShowSearch(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'h') {
        e.preventDefault();
        setShowSearch(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        handleRun();
      }
      if (e.altKey && e.shiftKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        handleFormatCode();
      }
      if (e.key === 'Escape' && showSearch) {
        setShowSearch(false);
        aceEditorRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showSearch, activeTab, handleFormatCode, handleRun]);

  // Open command in tab
  const handleOpenCommandInTab = (cmd: BotCommand) => {
    const existing = openTabs.find((t) => t.id === cmd.id);
    if (existing) {
      activeTabIdRef.current = existing.id;
      setActiveTabId(existing.id);
    } else {
      const newTab: OpenTabItem = {
        id: cmd.id,
        name: cmd.name,
        code: cmd.code || `# ${cmd.name}\nBot.sendMessage(Bot.getChatId(), "Hello from ${cmd.name}")\n`,
        commandRef: cmd,
        isModified: false,
      };
      setOpenTabs((prev) => [...prev, newTab]);
      activeTabIdRef.current = cmd.id;
      setActiveTabId(cmd.id);
    }
    setShowNewTabSelector(false);
    setNewTabSearch('');
  };

  // Close tab
  const handleCloseTab = (e: React.MouseEvent, tabId: string) => {
    e.stopPropagation();
    if (openTabs.length === 1) return; // Keep at least one tab
    const nextTabs = openTabs.filter((t) => t.id !== tabId);
    setOpenTabs(nextTabs);
    // Cleanup EditSession for closed tab
    const closingSession = sessionsRef.current.get(tabId);
    if (closingSession) {
      try {
        (closingSession as any)?.bgTokenizer?.stop?.();
      } catch (_) {}
    }
    sessionsRef.current.delete(tabId);
    if (activeTabId === tabId) {
      setActiveTabId(nextTabs[nextTabs.length - 1].id);
    }
  };

  // Undo & Redo (Strictly isolated per tab session with accurate baseline dirty tracking)
  const handleUndo = () => {
    if (aceEditorRef.current && canUndo) {
      aceEditorRef.current.undo();
      const session = aceEditorRef.current.getSession();
      const currentVal = session.getValue();
      const baseSaved = savedCodeMapRef.current.get(activeTabId) ?? '';
      const isDirty = currentVal !== baseSaved;
      const um = session.getUndoManager();

      setCanUndo(um.hasUndo());
      setCanRedo(um.hasRedo());
      setCanSave(isDirty);
      setOpenTabs((prev) =>
        prev.map((t) => (t.id === activeTabId ? { ...t, code: currentVal, isModified: isDirty } : t))
      );
      aceEditorRef.current.focus();
    }
  };

  const handleRedo = () => {
    if (aceEditorRef.current && canRedo) {
      aceEditorRef.current.redo();
      const session = aceEditorRef.current.getSession();
      const currentVal = session.getValue();
      const baseSaved = savedCodeMapRef.current.get(activeTabId) ?? '';
      const isDirty = currentVal !== baseSaved;
      const um = session.getUndoManager();

      setCanUndo(um.hasUndo());
      setCanRedo(um.hasRedo());
      setCanSave(isDirty);
      setOpenTabs((prev) =>
        prev.map((t) => (t.id === activeTabId ? { ...t, code: currentVal, isModified: isDirty } : t))
      );
      aceEditorRef.current.focus();
    }
  };

  // Save handler - only saved when modified
  const handleSave = async () => {
    if (!activeTab || !aceEditorRef.current) return;
    const currentCode = aceEditorRef.current.getValue();
    const tab = activeTab;
    const fullCmdObj: BotCommand = {
      ...(tab.commandRef || {}),
      id: tab.id,
      name: tab.name,
      code: currentCode,
    };
    // The code is sent to the server first. It is marked "saved" ONLY when the server confirms it.
    let res: any = { ok: true };
    try {
      if (onSaveCommand) res = (await onSaveCommand(fullCmdObj, currentCode, fullCmdObj)) || { ok: true };
    } catch (e: any) {
      res = { ok: false, error: e?.response?.data?.error || e?.message || 'Could not reach the server' };
    }
    if (res.ok === false) {
      // keep the draft and the "modified" mark: nothing is lost, nothing is pretended
      showNotification(`NOT saved: ${res.error || 'server error'}. Your code is still here — press Save again.`, 'error', 6000);
      return;
    }
    savedCodeMapRef.current.set(tab.id, currentCode);
    clearTimeout(draftTimers.current.get(tab.id));
    clearDraft(draftScopeRef.current, tab.id);
    setOpenTabs((prev) =>
      prev.map((t) => (t.id === tab.id ? { ...t, code: currentCode, commandRef: fullCmdObj, isModified: false } : t))
    );
    setCanSave(false);
    const errs = (res.errors || []) as { line: number; message: string }[];
    if (errs.length) {
      showNotification(`Saved ${tab.name} — but it has ${errs.length} error${errs.length > 1 ? 's' : ''} (line ${errs[0].line}: ${errs[0].message}). It will not run until fixed.`, 'warning', 7000);
    } else {
      showNotification(`Saved ${tab.name} successfully`, 'success');
    }
  };

  // Direct Paste Code handler (Paste Code)
  const handlePasteCodeDirect = async () => {
    if (!aceEditorRef.current) return;
    try {
      if (navigator.clipboard && typeof navigator.clipboard.readText === 'function') {
        const text = await navigator.clipboard.readText();
        if (text && text.trim()) {
          aceEditorRef.current.insert(text);
          aceEditorRef.current.focus();
          showNotification('Code pasted from clipboard 📋', 'success');
          return;
        }
      }
    } catch {
      // Browser denied clipboard access or iframe restrictions apply
    }
    setShowPasteModal(true);
  };

  const handleApplyPaste = (codeToInsert: string, replaceAll: boolean) => {
    if (!aceEditorRef.current) return;
    const session = aceEditorRef.current.getSession();
    if (replaceAll) {
      session.setValue(codeToInsert);
    } else {
      aceEditorRef.current.insert(codeToInsert);
    }
    aceEditorRef.current.focus();
    showNotification('Code pasted into editor 📋', 'success');
  };

  // Syntax Checker handler (Save / Check Syntax)
  const applyAnnotations = (res: SyntaxCheckResult) => {
    if (!aceEditorRef.current) return;
    const session = aceEditorRef.current.getSession();
    session.setAnnotations([
      ...res.errors.map((err) => ({
        row: Math.max(0, err.line - 1),
        column: Math.max(0, err.column - 1),
        text: err.message,
        type: 'error' as const,
      })),
      ...res.warnings.map((warn) => ({
        row: Math.max(0, warn.line - 1),
        column: Math.max(0, warn.column - 1),
        text: warn.message,
        type: 'warning' as const,
      })),
    ]);
  };

  const handleCheckSyntax = async () => {
    if (!aceEditorRef.current) return;
    const code = aceEditorRef.current.getValue();
    try {
      const res = await validateRemote(code);
      setSyntaxResult(res);
      applyAnnotations(res);
      if (res.isValid && res.warnings.length === 0) {
        showNotification('✓ No problems found.', 'success');
      }
      setShowSyntaxChecker(true);
    } catch {
      showNotification('Could not check the code right now.', 'info');
    }
  };

  // Live check while typing (debounced) — gutter markers only
  useEffect(() => {
    const editor = aceEditorRef.current;
    if (!editor) return;
    let timer: any = null;
    let seq = 0;
    const run = () => {
      const mySeq = ++seq;
      const code = editor.getValue();
      if (!code.trim()) { editor.getSession().setAnnotations([]); return; }
      validateRemote(code).then((res) => {
        if (mySeq === seq && aceEditorRef.current === editor) applyAnnotations(res);
      }).catch(() => {});
    };
    const onChange = () => { clearTimeout(timer); timer = setTimeout(run, 700); };
    editor.on('change', onChange);
    return () => { clearTimeout(timer); editor.off('change', onChange); };
  }, [activeTabId]);

  const handleJumpToLine = (line: number, column = 1) => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.gotoLine(line, column, true);
    aceEditorRef.current.focus();
  };

  // Open from Errors tab: jump to the failing line once editor is ready
  useEffect(() => {
    if (!initialJumpLine || initialJumpLine < 1) return;
    const t = window.setTimeout(() => {
      try { handleJumpToLine(Number(initialJumpLine), 1); } catch (_) {}
    }, 350);
    return () => clearTimeout(t);
  }, [initialJumpLine, activeTabId]);


  // Copy Code
  const handleCopyCode = () => {
    if (!aceEditorRef.current) return;
    const code = aceEditorRef.current.getValue();
    navigator.clipboard.writeText(code).then(() => {
      showNotification('Code copied to clipboard', 'info');
      setShowMobileMore(false);
    });
  };

  // Download Script strictly as Plain Text (.txt)
  const handleDownloadScript = () => {
    if (!activeTab || !aceEditorRef.current) return;
    const code = aceEditorRef.current.getValue();
    const cleanName = activeTab.name.replace(/[^a-zA-Z0-9_-]/g, '_') || 'command';
    const filename = `${cleanName}.txt`;
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    showNotification(`Downloaded ${filename} (Text File)`, 'info');
    setShowMobileMore(false);
  };

  // Upload & Import from .txt file
  const handleUploadTxtFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (typeof content === 'string' && aceEditorRef.current) {
        const session = aceEditorRef.current.getSession();
        session.setValue(content);
        showNotification(`Imported "${file.name}" (.txt file)`, 'success');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
    setShowMobileMore(false);
  };

  // Toggle Comment (#) on active line
  const handleToggleComment = () => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.toggleCommentLines();
    aceEditorRef.current.focus();
  };

  // Duplicate Current Line Down
  const handleDuplicateLine = () => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.copyLinesDown();
    aceEditorRef.current.focus();
  };

  // Delete Current Line
  const handleDeleteLine = () => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.removeLines();
    aceEditorRef.current.focus();
  };

  // Indent (Tab / 4 spaces)
  const handleIndent = () => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.blockIndent();
    aceEditorRef.current.focus();
  };

  // Outdent (Shift+Tab)
  const handleOutdent = () => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.blockOutdent();
    aceEditorRef.current.focus();
  };

  // Insert Quick Code Snippet
  const handleInsertCode = (codeStr: string) => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.insert(codeStr);
    aceEditorRef.current.focus();
  };

  // Insert Quick Character
  const handleInsertChar = (char: string) => {
    if (!aceEditorRef.current) return;
    aceEditorRef.current.insert(char);
    aceEditorRef.current.focus();
  };

  // Back handler
  const doLeave = () => {
    // flush drafts so nothing typed is lost
    sessionsRef.current.forEach((sess, id) => {
      const base = savedCodeMapRef.current.get(id) ?? '';
      const v = sess.getValue();
      if (v !== base) sessionDraft(draftScopeRef.current, id, sess);
    });
    if (onBack) onBack();
    else if (onClose) onClose();
  };
  const handleBack = () => {
    const dirty = openTabsRef.current.some((t) => t.isModified);
    if (dirty) setShowLeaveConfirm(true);
    else doLeave();
  };

  // flush drafts on refresh / close, and warn when there is unsaved work
  useEffect(() => {
    const flush = () => {
      sessionsRef.current.forEach((sess, id) => {
        const base = savedCodeMapRef.current.get(id) ?? '';
        const v = sess.getValue();
        if (v !== base) sessionDraft(draftScopeRef.current, id, sess);
      });
    };
    const warn = (e: BeforeUnloadEvent) => {
      flush();
      if (openTabsRef.current.some((t) => t.isModified)) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', warn);
    window.addEventListener('pagehide', flush);
    return () => { window.removeEventListener('beforeunload', warn); window.removeEventListener('pagehide', flush); };
  }, []);

  const applyPendingDraft = (accept: boolean) => {
    const d = pendingDraft;
    setPendingDraft(null);
    if (!d) return;
    if (accept) {
      const sess = sessionsRef.current.get(d.tabId);
      const saved = readDraft(draftScopeRef.current, d.tabId);
      if (sess) {
        sess.setValue(d.code);
        try { if (saved?.undo) sess.getUndoManager().fromJSON(saved.undo); } catch {}
        setCanUndo(sess.getUndoManager().hasUndo());
        setCanRedo(sess.getUndoManager().hasRedo());
        sessionDraft(draftScopeRef.current, d.tabId, sess, true);
      }
    } else {
      clearDraft(draftScopeRef.current, d.tabId);
    }
  };

  // Create new command directly from search / plus palette
  const handleCreateAndOpenCommand = (cmdName: string, folder: string = 'All') => {
    const trimmed = cmdName.trim();
    if (!trimmed) return;
    const formatted = trimmed;      // exactly what the user typed
    if ((allCommands || []).some((c: any) => c.name === formatted)) { showNotification(`The command "${formatted}" already exists`, 'info'); return; }
    const newCmd: BotCommand = {
      id: `cmd-${Date.now()}`,
      name: formatted,
      code: '',
      folder: folder.trim() || 'All',
    };
    if (onCreateCommand) {
      onCreateCommand(newCmd);
    }
    handleOpenCommandInTab(newCmd);
    setNewTabSearch('');
    setNewCmdNameInput('');
    setShowNewTabSelector(false);
    showNotification(`Created & opened tab for ${formatted}`, 'success');
  };

  const isErrorsTabActive = activeTabId === ERRORS_TAB_ID;

  const openErrorsTab = useCallback(() => {
    setOpenTabs((prev) => {
      if (prev.some((t) => t.id === ERRORS_TAB_ID)) return prev;
      return [...prev, { id: ERRORS_TAB_ID, name: 'Errors', code: '', isModified: false }];
    });
    activeTabIdRef.current = ERRORS_TAB_ID;
    setActiveTabId(ERRORS_TAB_ID);
    setShowNewTabSelector(false);
  }, []);


  // Mobile keyboard: lift quick bar above keyboard when enabled
  useEffect(() => {
    if (!quickBarAboveKeyboard) {
      setKeyboardLift(0);
      return;
    }
    const vv = window.visualViewport;
    if (!vv) return;
    const update = () => {
      const overlap = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      setKeyboardLift(overlap > 40 ? overlap : 0);
    };
    update();
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
    window.addEventListener('focusin', update);
    window.addEventListener('focusout', update);
    return () => {
      vv.removeEventListener('resize', update);
      vv.removeEventListener('scroll', update);
      window.removeEventListener('focusin', update);
      window.removeEventListener('focusout', update);
    };
  }, [quickBarAboveKeyboard]);

  const refreshErrors = useCallback(() => {
    if (!bot?.id) return;
    setLiveErrors(null);
    apiService
      .getBotErrors(bot.id)
      .then((d) => setLiveErrors(Array.isArray(d) ? d : []))
      .catch(() => setLiveErrors([]));
  }, [bot?.id]);

  // Load errors once when Errors tab opens (no polling — same data as Bot Studio Errors)
  useEffect(() => {
    if (!isErrorsTabActive || !bot?.id) return;
    let alive = true;
    setLiveErrors(null);
    apiService
      .getBotErrors(bot.id)
      .then((d) => {
        if (alive) setLiveErrors(Array.isArray(d) ? d : []);
      })
      .catch(() => {
        if (alive) setLiveErrors([]);
      });
    return () => {
      alive = false;
    };
  }, [isErrorsTabActive, bot?.id]);

  const openEditDetailsForTab = (tabId: string) => {
    if (tabId === ERRORS_TAB_ID) return;
    const tab = openTabsRef.current.find((t) => t.id === tabId);
    if (!tab) return;
    const ref = tab.commandRef;
    setEditDetailsTabId(tabId);
    setEditName(tab.name || '');
    setEditFolder(ref?.folder || 'All');
    setEditAliases((ref?.aliases || []).join(', '));
    setEditAdminOnly(!!ref?.isAdminOnly);
    setEditPinned(!!ref?.isPinned);
    setEditDetailsOpen(true);
  };

  const saveEditDetails = async () => {
    if (!editDetailsTabId || editDetailsTabId === ERRORS_TAB_ID) return;
    const name = editName.trim();
    if (!name) {
      showNotification('Command name is required', 'error');
      return;
    }
    const tab = openTabsRef.current.find((t) => t.id === editDetailsTabId);
    if (!tab) return;
    const aliases = editAliases
      .split(',')
      .map((a) => a.trim())
      .filter(Boolean);
    const meta: Partial<BotCommand> = {
      name,
      folder: editFolder.trim() || 'All',
      aliases,
      isAdminOnly: editAdminOnly,
      isPinned: editPinned,
    };
    const fullCmd: BotCommand = {
      ...(tab.commandRef || { id: tab.id, name: tab.name, code: tab.code }),
      ...meta,
      id: tab.commandRef?.id || tab.id,
      code: tab.code,
    };
    setEditSaving(true);
    try {
      if (onSaveCommand) {
        const res = await onSaveCommand(fullCmd, fullCmd.code, meta);
        if (res && typeof res === 'object' && res.ok === false) {
          showNotification(res.error || 'Could not save command details', 'error');
          setEditSaving(false);
          return;
        }
      }
      setOpenTabs((prev) =>
        prev.map((t) =>
          t.id === editDetailsTabId
            ? { ...t, name, commandRef: { ...fullCmd } }
            : t
        )
      );
      setEditDetailsOpen(false);
      setEditDetailsTabId(null);
      showNotification('Command details saved', 'success');
    } catch (e: any) {
      showNotification(e?.message || 'Could not save command details', 'error');
    } finally {
      setEditSaving(false);
    }
  };

  // Ensure available commands list is rich & populated
  const defaultCommandsList: BotCommand[] = [
    { id: 'cmd-start', name: '/start', code: `# Welcome command\nuser_id = Bot.getChatId()\nBot.sendMessage(user_id, "Welcome!")\n`, folder: 'Main' },
    { id: 'cmd-help', name: '/help', code: `# Help menu\nuser_id = Bot.getChatId()\nBot.sendMessage(user_id, "Available commands:\\n/start\\n/help\\n/balance")\n`, folder: 'Main' },
    { id: 'cmd-balance', name: '/balance', code: `# Balance\nuser_id = Bot.getChatId()\nBot.sendMessage(user_id, "Balance: $0.00")\n`, folder: 'Finance' },
    { id: 'cmd-deposit', name: '/deposit', code: `# Deposit\nuser_id = Bot.getChatId()\nBot.sendMessage(user_id, "Deposit menu")\n`, folder: 'Finance' },
    { id: 'cmd-withdraw', name: '/withdraw', code: `# Withdraw\nuser_id = Bot.getChatId()\nBot.sendMessage(user_id, "Withdraw menu")\n`, folder: 'Finance' },
    { id: 'cmd-settings', name: '/settings', code: `# Settings\nuser_id = Bot.getChatId()\nBot.sendMessage(user_id, "Bot Settings")\n`, folder: 'Settings' },
  ];

  const effectiveAllCommands = allCommands && allCommands.length > 0 ? allCommands : defaultCommandsList;

  // Filter commands for (+) search picker
  const filteredCommandsToOpen = effectiveAllCommands.filter((c) =>
    c.name.toLowerCase().includes(newTabSearch.toLowerCase())
  );

  return (
    <div
      id="telebot-fullscreen-ide"
      className={`fixed inset-0 z-50 w-full max-w-[100vw] h-[100dvh] max-h-[100dvh] flex flex-col overflow-hidden font-sans transition-colors duration-200 ${
        ideTheme === 'dark'
          ? 'bg-[#1e1e1e] text-slate-100'
          : 'bg-[#f8fafc] text-slate-900'
      }`}
      style={{ margin: 0, padding: 0 }}
    >
      {/* Run output */}
      {runOpen && (
        <div className="fixed bottom-0 inset-x-0 z-50 max-h-[55vh] sm:max-h-[45vh] flex flex-col bg-[#1e1e1e] text-gray-100 border-t border-[#3e3e42] shadow-2xl">
          <div className="flex flex-col gap-2 px-3 py-2 border-b border-[#3e3e42] text-xs">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 w-full min-w-0">
              <span className="font-bold shrink-0">Run / Test</span>
              <select
                value={runUpdateType}
                onChange={(e) => setRunUpdateType(e.target.value)}
                className="px-2 py-1.5 rounded bg-[#2a2a2d] border border-[#3e3e42] text-gray-100 outline-none w-full sm:w-auto sm:max-w-[180px] min-w-0"
                title="Telegram update type (message, pre_checkout_query, …). Special handlers: /handler_<type>"
              >
                <option value="message">message</option>
                <option value="callback_query">callback_query</option>
                <option value="pre_checkout_query">pre_checkout_query</option>
                <option value="inline_query">inline_query</option>
                <option value="shipping_query">shipping_query</option>
                <option value="edited_message">edited_message</option>
                <option value="my_chat_member">my_chat_member</option>
                <option value="chat_join_request">chat_join_request</option>
                <option value="poll">poll</option>
                <option value="poll_answer">poll_answer</option>
              </select>
              <div className="flex flex-col sm:flex-row gap-2 w-full min-w-0 sm:contents">
              <input value={runText} onChange={(e) => setRunText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleRun(); }}
                placeholder={runUpdateType === 'callback_query' ? 'callback text / label' : `Message / params (default ${activeTab?.name?.startsWith('/') ? activeTab.name : 'empty'})`}
                className="w-full sm:flex-1 min-w-0 px-2 py-1.5 rounded bg-[#2a2a2d] border border-[#3e3e42] text-gray-100 outline-none" />
              <div className="flex items-center gap-2 shrink-0">
              <button type="button" onClick={handleRun} disabled={runBusy} className="flex-1 sm:flex-none px-3 py-1.5 rounded bg-emerald-600 text-white font-bold disabled:opacity-60">Run</button>
              <button type="button" onClick={() => setRunOpen(false)} aria-label="Close" className="p-1.5 rounded hover:bg-[#38383c]"><X className="w-4 h-4" /></button>
              </div>
              </div>
            </div>
            {(runUpdateType === 'callback_query' || runCallbackData) && (
              <div className="flex items-center gap-2">
                <span className="text-gray-400 shrink-0">callback_data</span>
                <input
                  value={runCallbackData}
                  onChange={(e) => setRunCallbackData(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRun(); }}
                  placeholder="e.g. buy_pro or menu:settings"
                  className="flex-1 min-w-0 px-2 py-1 rounded bg-[#2a2a2d] border border-[#3e3e42] text-gray-100 outline-none"
                />
              </div>
            )}
            <div className="text-[10px] text-gray-500">
              All updates also reach <code className="text-sky-400">*</code> when no specific command matches.
              Special handlers: <code className="text-sky-400">/handler_{'{'}update_type{'}'}</code> (e.g. /handler_pre_checkout_query).
              Missing params / message.text → <code className="text-amber-300">None</code> (never empty string).
            </div>
          </div>
          <div className="p-3 overflow-y-auto font-mono text-[12px] space-y-2">
            {runBusy && <div className="text-gray-400">Running…</div>}
            {!runBusy && runResult && (
              <>
                <div className={runResult.ok ? 'text-emerald-400' : 'text-red-400'}>
                  {runResult.ok ? `✓ Finished in ${runResult.durationMs} ms` : `✗ ${runResult.error || 'The command stopped with an error.'}`}
                </div>
                {(runResult.calls || []).length === 0 && runResult.ok && <div className="text-gray-400">The command ran and sent nothing to Telegram.</div>}
                {(runResult.calls || []).map((c: any, i: number) => (
                  <div key={i} className="rounded bg-[#252526] p-2">
                    <div className="text-sky-300">{c.method}</div>
                    <pre className="whitespace-pre-wrap break-all text-gray-300">{JSON.stringify(c.params, null, 2)}</pre>
                  </div>
                ))}
                <div className="text-[11px] text-gray-500">Test run: messages are not sent to real users, and saved data is not changed.</div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Visual Feedback Toast Notification */}
      {feedbackToast && (
        <div className={`fixed top-3 left-1/2 -translate-x-1/2 z-60 max-w-[92vw] px-4 py-2 rounded-xl backdrop-blur-md text-white text-xs font-semibold shadow-2xl border flex items-center gap-2 animate-in fade-in slide-in-from-top-3 duration-200 ${feedbackToast.type === 'error' ? 'bg-rose-700/95 border-rose-400' : feedbackToast.type === 'warning' ? 'bg-amber-700/95 border-amber-400' : 'bg-slate-900/95 border-slate-700'}`}>
          <Check className={`w-4 h-4 shrink-0 ${feedbackToast.type === 'error' ? 'text-rose-200' : feedbackToast.type === 'warning' ? 'text-amber-200' : 'text-emerald-400'}`} />
          <span>{feedbackToast.message}</span>
        </div>
      )}

      {/* 1. COMMAND TABS: Clean VS Code styled tabs with scroll navigation for PC & mobile */}
      <div
        className={`flex items-stretch gap-0.5 border-b px-1.5 pt-1 shrink-0 overflow-hidden ${
          ideTheme === 'dark'
            ? 'bg-[#181818] border-[#2d2d30]'
            : 'bg-[#e2e8f0] border-slate-300'
        }`}
      >
        {/* Horizontal tabs container with smooth mouse wheel and touch scrolling */}
        <div
          ref={tabsScrollContainerRef}
          onWheel={(e) => {
            if (e.deltaY !== 0) {
              e.currentTarget.scrollLeft += e.deltaY;
            }
          }}
          className={`flex items-stretch gap-1 overflow-x-auto flex-1 min-w-0 py-0.5 touch-pan-x overscroll-contain scrollbar-thin ${
            ideTheme === 'dark'
              ? 'scrollbar-thumb-[#3e3e42] scrollbar-track-[#181818]'
              : 'scrollbar-thumb-slate-400 scrollbar-track-slate-200'
          }`}
          style={{ WebkitOverflowScrolling: 'touch' }}
        >
          {openTabs.map((tab) => {
            const isSelected = tab.id === activeTabId;
            const isErrors = tab.id === ERRORS_TAB_ID;
            return (
              <div
                key={tab.id}
                data-tab-id={tab.id}
                onClick={() => setActiveTabId(tab.id)}
                onMouseDown={(e) => {
                  if (e.button === 1) {
                    e.preventDefault();
                    handleCloseTab(e, tab.id);
                  }
                }}
                title={tab.name}
                className={`group flex items-center gap-1.5 px-2.5 py-1.5 rounded-t-md cursor-pointer select-none whitespace-nowrap text-xs border border-b-0 transition-all duration-150 shrink-0 ${
                  isSelected
                    ? ideTheme === 'dark'
                      ? `bg-[#1e1e1e] text-white border-[#333] border-t-2 ${isErrors ? 'border-t-rose-500' : 'border-t-blue-500'} font-medium`
                      : `bg-white text-slate-900 border-slate-300 border-t-2 ${isErrors ? 'border-t-rose-600' : 'border-t-blue-600'} font-bold shadow-xs`
                    : ideTheme === 'dark'
                      ? 'bg-transparent text-gray-400 border-transparent hover:bg-[#252526] hover:text-gray-200'
                      : 'bg-transparent text-slate-600 border-transparent hover:bg-slate-300/60 hover:text-slate-900'
                }`}
              >
                {isErrors ? (
                  <Bug className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                ) : (
                  <span className="text-[9px] font-bold px-1.5 py-0.2 rounded font-mono uppercase bg-emerald-500/20 text-emerald-600 dark:text-emerald-300">
                    PY
                  </span>
                )}
                <span className="max-w-[120px] sm:max-w-[160px] truncate font-mono">{tab.name}</span>
                {tab.isModified && !isErrors && (
                  <span
                    className="w-2 h-2 rounded-full bg-amber-400 shrink-0"
                    title="Unsaved changes"
                  />
                )}
                {openTabs.length > 1 && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCloseTab(e, tab.id);
                    }}
                    className="w-4 h-4 grid place-items-center rounded text-gray-400 hover:bg-black/10 dark:hover:bg-white/15 hover:text-red-500 dark:hover:text-white opacity-70 group-hover:opacity-100 transition cursor-pointer"
                    aria-label={`Close ${tab.name}`}
                  >
                    ×
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Add Tab button (Scroll left/right buttons removed per user request) */}
        <div className="flex items-center shrink-0 px-1">
          <button
            type="button"
            onClick={() => {
              setShowNewTabSelector(true);
              setTimeout(() => newTabSearchInputRef.current?.focus(), 50);
            }}
            title="Open or create command tab (+)"
            aria-label="Open or create command tab"
            className={`w-6 h-6 rounded-md transition-colors flex items-center justify-center cursor-pointer font-bold text-sm shadow-xs border ${
              ideTheme === 'dark'
                ? 'text-gray-300 hover:text-white bg-[#252526] hover:bg-[#333] border-[#3e3e42]'
                : 'text-slate-700 hover:text-slate-950 bg-white hover:bg-slate-200 border-slate-300'
            }`}
          >
            +
          </button>
        </div>
      </div>

      
      
      {/* 2. SINGLE-ROW TOOLBAR — critical tools first; hidden on Errors */}
      {!isErrorsTabActive && (
        <div
          className={`shrink-0 border-b w-full max-w-[100vw] overflow-x-auto ${
            ideTheme === 'dark' ? 'bg-[#252526] border-[#2d2d30]' : 'bg-slate-100 border-slate-300'
          }`}
          style={{ WebkitOverflowScrolling: 'touch' }}
        >
          <div className="flex items-center gap-0.5 px-1.5 py-1 min-h-[40px]">
            <button type="button" onClick={handleBack} title="Back to command list" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-[#333337] text-gray-200 border-transparent hover:bg-[#3e3e42]' : 'bg-white text-slate-800 border-slate-300 hover:bg-slate-200'}`}>
              <ArrowLeft className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={handleUndo} disabled={!canUndo} title="Undo (Ctrl+Z)" className={`p-1.5 rounded-md shrink-0 cursor-pointer disabled:opacity-30 ${ideTheme === 'dark' ? 'text-gray-200 hover:bg-[#333]' : 'text-slate-800 hover:bg-slate-200'}`}>
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={handleRedo} disabled={!canRedo} title="Redo (Ctrl+Y)" className={`p-1.5 rounded-md shrink-0 cursor-pointer disabled:opacity-30 ${ideTheme === 'dark' ? 'text-gray-200 hover:bg-[#333]' : 'text-slate-800 hover:bg-slate-200'}`}>
              <RotateCw className="w-3.5 h-3.5" />
            </button>
            <span className={`w-px h-4 shrink-0 ${ideTheme === 'dark' ? 'bg-[#3e3e42]' : 'bg-slate-300'}`} />
            <button type="button" onClick={() => { setShowSearch((prev) => { const next = !prev; if (next) setTimeout(() => searchInputRef.current?.focus(), 50); return next; }); }} title="Search / Find (Ctrl+F)" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${showSearch ? 'bg-blue-600 text-white border-blue-500' : ideTheme === 'dark' ? 'bg-[#2d2d30] text-gray-300 border-[#3e3e42]' : 'bg-white text-slate-700 border-slate-300'}`}>
              <Search className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => {
                const tab = openTabsRef.current.find((x) => x.id === activeTabId);
                const cmd = tab?.commandRef || (tab ? { id: tab.id, name: tab.name, code: tab.code } as BotCommand : null);
                if (cmd && onRequestEditCommand) onRequestEditCommand(cmd);
                else if (tab && tab.id !== ERRORS_TAB_ID) openEditDetailsForTab(tab.id);
              }}
              title="Edit command details (name, folder, aliases, pin, admin)"
              className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-[#2a2a2d] text-blue-300 border-[#3e3e42] hover:bg-[#38383c]' : 'bg-white text-blue-600 border-slate-300 hover:bg-blue-50'}`}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={handleRun} disabled={runBusy} title="Run / Test (Ctrl+Enter)" className="px-2 py-1 rounded-md text-[11px] font-bold flex items-center gap-1 shrink-0 cursor-pointer bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-60">
              <Play className="w-3 h-3" /><span>{runBusy ? '…' : 'Run'}</span>
            </button>
            <button type="button" onClick={handleSave} disabled={!canSave} title="Save (Ctrl+S)" className={`px-2.5 py-1 rounded-md text-[11px] font-bold flex items-center gap-1 shrink-0 transition ${canSave ? 'bg-blue-600 hover:bg-blue-500 text-white cursor-pointer' : ideTheme === 'dark' ? 'bg-[#2a2a2d] text-gray-500 opacity-40 cursor-not-allowed border border-[#3e3e42]' : 'bg-slate-200 text-slate-400 opacity-50 cursor-not-allowed border border-slate-300'}`}>
              <Save className="w-3 h-3" /><span>Save</span>
            </button>
            <button type="button" onClick={handleFormatCode} title="Format code (Alt+Shift+F)" className={`px-2 py-1 rounded-md text-[11px] font-bold flex items-center gap-1 shrink-0 cursor-pointer border ${ideTheme === 'dark' ? 'bg-[#2a2a2d] text-gray-200 border-[#3e3e42]' : 'bg-white text-slate-700 border-slate-300'}`}>
              <Wand2 className="w-3 h-3" /><span>Format</span>
            </button>
            
            
            
            <span className={`w-px h-4 shrink-0 ${ideTheme === 'dark' ? 'bg-[#3e3e42]' : 'bg-slate-300'}`} />
            <button type="button" onClick={handlePasteCodeDirect} title="Paste code from clipboard" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-[#2d2d30] text-sky-300 border-sky-500/30' : 'bg-white text-sky-700 border-sky-300'}`}>
              <Clipboard className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={handleCheckSyntax} title="Check Python syntax" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-indigo-600/30 text-indigo-200 border-indigo-500/40' : 'bg-white text-indigo-700 border-indigo-300'}`}>
              <ShieldCheck className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => setIsWordWrap(!isWordWrap)} title="Toggle word wrap" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${isWordWrap ? (ideTheme === 'dark' ? 'bg-[#3e3e42] text-blue-400 border-blue-500/40' : 'bg-blue-100 text-blue-700 border-blue-300') : ideTheme === 'dark' ? 'bg-[#2d2d30] text-gray-400 border-[#3e3e42]' : 'bg-white text-slate-600 border-slate-300'}`}>
              <WrapText className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => setIdeTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))} title="Toggle light / dark theme" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-[#2d2d30] text-amber-300 border-[#3e3e42]' : 'bg-white text-amber-600 border-slate-300'}`}>
              {ideTheme === 'dark' ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            </button>
            <button type="button" onClick={handleCopyCode} title="Copy all code" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-[#2d2d30] text-gray-300 border-[#3e3e42]' : 'bg-white text-slate-700 border-slate-300'}`}>
              <Copy className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => fileInputRef.current?.click()} title="Import code from file" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-[#2d2d30] text-gray-300 border-[#3e3e42]' : 'bg-white text-slate-700 border-slate-300'}`}>
              <Upload className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={handleDownloadScript} title="Download as .txt" className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${ideTheme === 'dark' ? 'bg-[#2d2d30] text-gray-300 border-[#3e3e42]' : 'bg-white text-slate-700 border-slate-300'}`}>
              <Download className="w-3.5 h-3.5" />
            </button>
            <div className={`flex items-center rounded-md overflow-hidden text-xs border shrink-0 ${ideTheme === 'dark' ? 'bg-[#2d2d30] border-[#3e3e42]' : 'bg-white border-slate-300'}`} title="Font size">
              <button type="button" onClick={handleDecreaseFontSize} disabled={fontSize <= 2} className="px-1.5 py-1 disabled:opacity-30 cursor-pointer"><Minus className="w-2.5 h-2.5" /></button>
              <span className="px-1 text-[10px] font-mono font-bold tabular-nums">{fontSize}</span>
              <button type="button" onClick={handleIncreaseFontSize} disabled={fontSize >= 30} className="px-1.5 py-1 disabled:opacity-30 cursor-pointer"><Plus className="w-2.5 h-2.5" /></button>
            </div>
            
            
            <button
              type="button"
              onClick={() => setQuickBarAboveKeyboard((v) => !v)}
              title={quickBarAboveKeyboard ? 'Quick bar follows keyboard (on)' : 'Quick bar follows keyboard (off)'}
              className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${quickBarAboveKeyboard ? 'bg-blue-600 text-white border-blue-500' : ideTheme === 'dark' ? 'bg-[#2d2d30] text-gray-300 border-[#3e3e42]' : 'bg-white text-slate-700 border-slate-300'}`}
            >
              <Type className="w-3.5 h-3.5" />
            </button>
<button
              type="button"
              onClick={() => setShowHelp((v) => !v)}
              title="Editor help — tools & shortcuts"
              className={`p-1.5 rounded-md shrink-0 border cursor-pointer ${showHelp ? 'bg-blue-600 text-white border-blue-500' : ideTheme === 'dark' ? 'bg-[#2d2d30] text-gray-300 border-[#3e3e42]' : 'bg-white text-slate-700 border-slate-300'}`}
            >
              <HelpCircle className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

{/* 3. RESPONSIVE FIND & REPLACE DRAWER */}
      {showSearch && (
        <div
          id="ide-search-drawer"
          className="px-3 py-2 bg-[#252526] border-b border-[#333] flex flex-wrap items-center gap-2 text-xs z-30 shadow-2xl"
        >
          {/* Find Input */}
          <div className="flex items-center gap-1.5 bg-[#1e1e1e] px-2.5 py-1.5 rounded-lg border border-[#3e3e42] flex-1 min-w-[170px]">
            <Search className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleFind(e.shiftKey);
                }
              }}
              placeholder="Find in file (Enter for next)..."
              className="bg-transparent text-white font-mono text-xs w-full focus:outline-none placeholder-gray-500"
              autoFocus
            />
            {searchQuery && (
              <span className="text-[10px] text-gray-400 shrink-0 font-mono px-1">
                {matchCount > 0 ? `${matchCount} found` : 'No match'}
              </span>
            )}
          </div>

          {/* Match Options: Case sensitive (Aa), Whole word (|ab|), Regex (.*) */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setMatchCase(!matchCase)}
              className={`px-2 py-1 rounded text-xs font-mono font-bold transition-colors cursor-pointer border ${
                matchCase
                  ? 'bg-blue-600 text-white border-blue-500'
                  : 'bg-[#333337] text-gray-400 border-[#444] hover:text-white'
              }`}
              title="Match Case (Aa)"
            >
              Aa
            </button>
            <button
              type="button"
              onClick={() => setMatchWholeWord(!matchWholeWord)}
              className={`px-2 py-1 rounded text-xs font-mono font-bold transition-colors cursor-pointer border ${
                matchWholeWord
                  ? 'bg-blue-600 text-white border-blue-500'
                  : 'bg-[#333337] text-gray-400 border-[#444] hover:text-white'
              }`}
              title="Match Whole Word (|ab|)"
            >
              |ab|
            </button>
            <button
              type="button"
              onClick={() => setUseRegex(!useRegex)}
              className={`px-2 py-1 rounded text-xs font-mono font-bold transition-colors cursor-pointer border ${
                useRegex
                  ? 'bg-blue-600 text-white border-blue-500'
                  : 'bg-[#333337] text-gray-400 border-[#444] hover:text-white'
              }`}
              title="Regular Expression (.*)"
            >
              .*
            </button>
          </div>

          {/* Prev / Next Navigation */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => handleFind(true)}
              className="p-1.5 rounded bg-[#333337] hover:bg-[#3e3e42] text-gray-300 hover:text-white border border-[#444] transition-colors cursor-pointer"
              title="Previous Match (Shift+Enter)"
            >
              <ChevronUp className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => handleFind(false)}
              className="p-1.5 rounded bg-[#333337] hover:bg-[#3e3e42] text-gray-300 hover:text-white border border-[#444] transition-colors cursor-pointer"
              title="Next Match (Enter)"
            >
              <ChevronDown className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="h-4 w-px bg-[#444] mx-0.5 hidden sm:block" />

          {/* Replace Input */}
          <div className="flex items-center gap-1.5 bg-[#1e1e1e] px-2.5 py-1.5 rounded-lg border border-[#3e3e42] flex-1 min-w-[170px]">
            <input
              type="text"
              value={replaceQuery}
              onChange={(e) => setReplaceQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleReplace();
                }
              }}
              placeholder="Replace with..."
              className="bg-transparent text-white font-mono text-xs w-full focus:outline-none placeholder-gray-500"
            />
          </div>

          {/* Replace & Replace All Buttons */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={handleReplace}
              className="px-2.5 py-1.5 rounded-lg bg-[#333337] hover:bg-[#3e3e42] text-gray-200 hover:text-white font-semibold text-xs cursor-pointer border border-[#444] transition-colors"
            >
              Replace
            </button>
            <button
              type="button"
              onClick={handleReplaceAll}
              className="px-2.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs cursor-pointer transition-colors shadow-xs"
            >
              Replace All
            </button>
          </div>

          {/* Close Search Drawer */}
          <button
            type="button"
            onClick={() => {
              setShowSearch(false);
              aceEditorRef.current?.focus();
            }}
            className="p-1 rounded text-gray-400 hover:text-white hover:bg-white/10 cursor-pointer ml-auto"
            title="Close Search (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 4. ACE CODE EDITOR WORKSPACE (Full Viewport Height) */}
      <div
        className="flex-1 w-full h-full relative overflow-hidden transition-colors"
        style={{ backgroundColor: ideTheme === 'dark' ? '#1e1e1e' : '#ffffff' }}
      >
        <div
          ref={editorContainerRef}
          id="telebot-studio-editor-viewport"
          className={`w-full h-full min-h-[400px] text-left ${ideTheme === 'light' ? 'ace-light-mode' : ''}`}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: ideTheme === 'dark' ? '#1e1e1e' : '#ffffff',
            fontFamily:
              'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
            visibility: isErrorsTabActive ? 'hidden' : 'visible',
          }}
        />
        {/* Errors tab — same content as Bot Studio Errors tab (stays open; does not auto-leave) */}
        {isErrorsTabActive && (
          <div
            className="absolute inset-0 z-10 overflow-y-auto p-4 sm:p-6"
            style={{ backgroundColor: ideTheme === 'dark' ? '#1e1e1e' : '#f8fafc' }}
          >
            <div className={`max-w-3xl mx-auto rounded-3xl border p-5 sm:p-6 space-y-4 ${ideTheme === 'dark' ? 'bg-[#252526] border-[#333]' : 'bg-white border-slate-200'}`}>
              <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-700 gap-3">
                <div className="min-w-0">
                  <h2 className={`text-lg font-bold ${ideTheme === 'dark' ? 'text-white' : 'text-slate-900'}`}>Errors</h2>
                  <p className="text-xs text-slate-500 mt-0.5">Every command failure from the last 30 days.</p>
                </div>
                <div className="flex items-center gap-2 shrink-0 flex-wrap">
                  <select
                    value={errorTimeFormat}
                    onChange={(e) => setErrorTimeFormat(e.target.value as 'local' | 'utc' | 'relative')}
                    className="px-2 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-bold border border-slate-200 dark:border-slate-700 cursor-pointer"
                    title="Error time display"
                  >
                    <option value="local">Local</option>
                    <option value="utc">UTC</option>
                    <option value="relative">Relative</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => setIdeTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))}
                    className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 text-xs font-bold cursor-pointer"
                    title="Toggle Errors tab theme"
                  >
                    {ideTheme === 'dark' ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    type="button"
                    onClick={refreshErrors}
                    className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 text-xs font-bold cursor-pointer"
                    title="Refresh errors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    disabled={!liveErrors || liveErrors.length === 0}
                    onClick={() => setConfirmClearErrors(true)}
                    className="px-3.5 py-1.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 text-xs font-bold cursor-pointer disabled:opacity-40"
                  >
                    Clear
                  </button>
                </div>
              </div>
              {liveErrors === null ? (
                <p className="text-xs text-slate-500">Loading…</p>
              ) : liveErrors.length === 0 ? (
                <div className={`p-12 text-center rounded-2xl border ${ideTheme === 'dark' ? 'bg-[#1e1e1e] border-[#333]' : 'bg-slate-50 border-slate-200'}`}>
                  <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 flex items-center justify-center mx-auto mb-3">
                    <Check className="w-6 h-6" />
                  </div>
                  <h4 className={`text-sm font-bold ${ideTheme === 'dark' ? 'text-white' : 'text-slate-900'}`}>No errors in the last 30 days.</h4>
                </div>
              ) : (
                <div className="space-y-2">
                  {liveErrors.map((er) => (
                    <div key={er.id} className="rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50/60 dark:bg-red-950/20 p-3 text-xs">
                      <button type="button" className="w-full text-left cursor-pointer" onClick={() => setOpenErrId(openErrId === er.id ? null : er.id)}>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono font-bold text-red-600 dark:text-red-400">{er.command || '(no command)'}</span>
                          <span className="text-[11px] text-slate-500">{er.time ? formatErrorTime(er.time) : ''}{er.line ? ` · line ${er.line}` : ''}</span>
                        </div>
                        <div className={`mt-1 break-words ${ideTheme === 'dark' ? 'text-slate-200' : 'text-slate-800'}`}>{er.message}</div>
                      </button>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="px-2.5 py-1.5 rounded-lg text-[11px] font-bold bg-slate-900 text-white dark:bg-white dark:text-slate-900 cursor-pointer hover:opacity-90"
                          onClick={(e) => {
                            e.stopPropagation();
                            const name = String(er.command || '').trim();
                            const cmd =
                              effectiveAllCommands.find((c) => c.name === name) ||
                              effectiveAllCommands.find((c) => c.name === `/${name.replace(/^\//, '')}`) ||
                              effectiveAllCommands.find((c) => (c.aliases || []).includes(name));
                            if (!cmd) {
                              showNotification(name ? `Command "${name}" not found in this bot` : 'No command on this error', 'info');
                              return;
                            }
                            // Open command tab but user stays in control — does not force-leave Errors until they switch
                            handleOpenCommandInTab(cmd);
                            showNotification(`Opened ${cmd.name}`, 'success');
                          }}
                        >
                          Open in editor
                        </button>
                        {er.stack && openErrId === er.id && (
                          <pre className={`w-full text-[10px] font-mono whitespace-pre-wrap max-h-40 overflow-auto rounded-lg p-2 mt-1 ${ideTheme === 'dark' ? 'bg-black/40 text-gray-400' : 'bg-white text-slate-500'}`}>
                            {er.stack}
                          </pre>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {confirmClearErrors && (
                <div className="fixed inset-0 z-[320] flex items-center justify-center p-4 bg-black/50" onClick={() => setConfirmClearErrors(false)}>
                  <div className={`w-full max-w-sm rounded-2xl p-5 space-y-3 shadow-2xl ${ideTheme === 'dark' ? 'bg-slate-900 border border-slate-700' : 'bg-white'}`} onClick={(e) => e.stopPropagation()}>
                    <h3 className={`text-sm font-black ${ideTheme === 'dark' ? 'text-white' : 'text-slate-900'}`}>Clear all errors?</h3>
                    <p className="text-xs text-slate-500">This permanently deletes every error log of this bot. It cannot be undone.</p>
                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={() => setConfirmClearErrors(false)} className="px-3 py-2 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 cursor-pointer">Cancel</button>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            if (bot?.id) {
                              await apiService.clearBotErrors(bot.id);
                              setLiveErrors([]);
                              showNotification('Error log cleared', 'success');
                            }
                          } catch (e: any) {
                            showNotification(e?.message || 'Could not clear errors', 'error');
                          }
                          setConfirmClearErrors(false);
                        }}
                        className="px-3 py-2 rounded-xl text-xs font-bold bg-red-600 hover:bg-red-700 text-white cursor-pointer"
                      >
                        Clear errors
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
        <style>{`
          .ace-light-mode,
          .ace-light-mode .ace_scroller,
          .ace-light-mode .ace_content {
            background-color: #ffffff !important;
            color: #0f172a !important;
          }
          .ace-light-mode .ace_gutter {
            background-color: #f8fafc !important;
            color: #64748b !important;
            border-right: 1px solid #e2e8f0 !important;
          }
          .ace-light-mode .ace_gutter-active-line {
            background-color: #e2e8f0 !important;
          }
          .ace-light-mode .ace_active-line {
            background-color: #f1f5f9 !important;
          }
          .ace-light-mode .ace_cursor {
            color: #0284c7 !important;
            border-left: 2px solid #0284c7 !important;
          }
          .ace-light-mode .ace_keyword {
            color: #b45309 !important;
            font-weight: 700;
          }
          .ace-light-mode .ace_string {
            color: #15803d !important;
          }
          .ace-light-mode .ace_comment {
            color: #64748b !important;
            font-style: italic;
          }
          .ace-light-mode .ace_constant.ace_numeric {
            color: #2563eb !important;
            font-weight: 600;
          }
          .ace-light-mode .ace_function {
            color: #7c3aed !important;
            font-weight: 600;
          }
          .ace-light-mode .ace_variable {
            color: #0f172a !important;
          }
          .ace-light-mode .ace_operator {
            color: #0284c7 !important;
            font-weight: 600;
          }
          .ace-light-mode .ace_marker-layer .ace_selection {
            background: #bae6fd !important;
          }
          .ace-light-mode .ace_marker-layer .ace_bracket {
            border: 1px solid #0284c7 !important;
          }
        `}</style>
      </div>

      
      
      {/* 5. MOBILE QUICK HELPER BAR — typing helpers + Bot methods + snippets */}
      {!isErrorsTabActive && (
      <div
        className="flex md:hidden items-center gap-1 px-1.5 py-1 min-h-[40px] bg-[#1e1e1e] border-t border-[#333] overflow-x-auto scrollbar-none shrink-0 text-[11px] font-mono select-none z-30"
        style={keyboardLift > 0 ? { position: 'fixed', left: 0, right: 0, bottom: keyboardLift, zIndex: 40 } : undefined}
      >
        <button type="button" onClick={() => handleInsertChar('    ')} className="px-2 py-1 rounded bg-[#333337] text-blue-300 font-bold shrink-0" title="Tab indent">Tab</button>
        <button type="button" onClick={() => handleInsertChar(':')} className="w-7 h-7 rounded bg-[#333337] text-amber-300 font-bold flex items-center justify-center shrink-0">:</button>
        <button type="button" onClick={() => handleInsertChar('()')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">()</button>
        <button type="button" onClick={() => handleInsertChar('[]')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">[]</button>
        <button type="button" onClick={() => handleInsertChar('{}')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">{'{}'}</button>
        <button type="button" onClick={() => handleInsertChar('""')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">&quot;&quot;</button>
        <button type="button" onClick={() => handleInsertChar("''")} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">&apos;&apos;</button>
        <button type="button" onClick={() => handleInsertChar('f""')} className="px-1.5 py-1 rounded bg-[#333337] text-emerald-300 font-bold shrink-0">f&quot;&quot;</button>
        <button type="button" onClick={() => handleInsertChar(' = ')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">=</button>
        <button type="button" onClick={() => handleInsertChar(' == ')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">==</button>
        <button type="button" onClick={() => handleInsertChar(' != ')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-200 font-bold shrink-0">!=</button>
        <button type="button" onClick={() => handleInsertChar(' and ')} className="px-1.5 py-1 rounded bg-[#333337] text-violet-300 font-bold shrink-0">and</button>
        <button type="button" onClick={() => handleInsertChar(' or ')} className="px-1.5 py-1 rounded bg-[#333337] text-violet-300 font-bold shrink-0">or</button>
        <button type="button" onClick={() => handleInsertChar(' not ')} className="px-1.5 py-1 rounded bg-[#333337] text-violet-300 font-bold shrink-0">not</button>
        <button type="button" onClick={() => handleInsertChar('if :\n    ')} className="px-1.5 py-1 rounded bg-[#333337] text-sky-300 font-bold shrink-0">if</button>
        <button type="button" onClick={() => handleInsertChar('for  in :\n    ')} className="px-1.5 py-1 rounded bg-[#333337] text-sky-300 font-bold shrink-0">for</button>
        <button type="button" onClick={() => handleInsertChar('while :\n    ')} className="px-1.5 py-1 rounded bg-[#333337] text-sky-300 font-bold shrink-0">while</button>
        <button type="button" onClick={() => handleInsertChar('try:\n    pass\nexcept Exception as e:\n    bot.sendMessage(str(e))')} className="px-1.5 py-1 rounded bg-rose-500/15 text-rose-300 border border-rose-500/30 font-bold shrink-0" title="try / except snippet">try/except</button>
        <button type="button" onClick={() => handleInsertChar('pass')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-300 font-bold shrink-0">pass</button>
        <button type="button" onClick={() => handleInsertChar('return')} className="px-1.5 py-1 rounded bg-[#333337] text-gray-300 font-bold shrink-0">return</button>
        <button type="button" onClick={() => handleInsertChar('bot.sendMessage("text")')} className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 shrink-0">bot.sendMessage</button>
        <button type="button" onClick={() => handleInsertChar('Bot.getChatId()')} className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 shrink-0">Bot.getChatId</button>
        <button type="button" onClick={() => handleInsertChar('bot.editMessageText("text")')} className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 shrink-0">editMessageText</button>
        <button type="button" onClick={() => handleInsertChar('bot.answerCallbackQuery()')} className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 shrink-0">answerCallbackQuery</button>
        <button type="button" onClick={() => handleInsertChar('bot.deleteMessage()')} className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 shrink-0">deleteMessage</button>
        <button type="button" onClick={() => handleInsertChar('bot.sendPhoto(photo="URL")')} className="px-2 py-1 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 shrink-0">sendPhoto</button>
        <button type="button" onClick={() => handleInsertChar('Bot.saveData("key", value)')} className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 shrink-0">Bot.saveData</button>
        <button type="button" onClick={() => handleInsertChar('Bot.getData("key")')} className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 shrink-0">Bot.getData</button>
        <button type="button" onClick={() => handleInsertChar('Bot.handleNextCommand("/next")')} className="px-2 py-1 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 shrink-0">handleNextCommand</button>
        <button type="button" onClick={() => handleInsertChar('message.text')} className="px-2 py-1 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 shrink-0">message.text</button>
        <button type="button" onClick={() => handleInsertChar('message.chat.id')} className="px-2 py-1 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 shrink-0">message.chat.id</button>
        <button type="button" onClick={() => handleInsertChar('call.data')} className="px-2 py-1 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 shrink-0">call.data</button>
        <button type="button" onClick={() => handleInsertChar('bot.sendMessage("Choose:", reply_markup={"inline_keyboard":[[{"text":"OK","callback_data":"ok"}]]})')} className="px-2 py-1 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 shrink-0" title="Inline keyboard snippet">inline_keyboard</button>
      </div>
      )}

{/* 6. STATUS BAR — hidden on Errors tab */}
      {!isErrorsTabActive && (
      <footer className="h-7 px-3 sm:px-4 bg-[#007acc] text-white flex items-center justify-between text-[11px] font-mono shrink-0 select-none shadow-inner">
        <div className="flex items-center gap-2 sm:gap-3 truncate">
          <span className="font-semibold">{activeMode.toUpperCase()} / BMP</span>
          <span className="opacity-60">•</span>
          <span>Spaces: 4</span>
          <span className="opacity-60 hidden sm:inline">•</span>
          <span className="hidden sm:inline">UTF-8</span>
          <span className="opacity-60 hidden md:inline">•</span>
          <button
            type="button"
            onClick={handleCheckSyntax}
            className="hidden md:flex items-center gap-1 hover:underline cursor-pointer opacity-90 hover:opacity-100 font-sans font-bold"
            title="Check Python Syntax & Lint"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Check Syntax</span>
          </button>
        </div>

        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <span>
            Ln {cursorPos.line}, Col {cursorPos.col}
          </span>
          <span className="opacity-60">•</span>
          <span>{editorLineCount} lines</span>
          <span className="opacity-60 hidden sm:inline">•</span>
          {activeTab?.isModified ? (
            <span className="text-amber-200 font-bold hidden sm:inline">● Unsaved</span>
          ) : (
            <span className="text-emerald-200 font-bold hidden sm:inline">✓ Saved</span>
          )}
        </div>
      </footer>
      )}

      {/* 7. PLUS (+) COMMAND SELECTOR MODAL - Global popover to switch / create command tabs */}
      {showNewTabSelector && (
        <div
          className="fixed inset-0 z-70 flex items-center justify-center p-3 sm:p-4 bg-black/75 backdrop-blur-xs overscroll-contain"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowNewTabSelector(false);
          }}
        >
          <div
            ref={newTabDropdownRef}
            className="w-full max-w-lg bg-[#252526] border border-[#3e3e42] rounded-2xl sm:rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] sm:max-h-[80vh] my-auto animate-in fade-in zoom-in-95 duration-150"
          >
            {/* Search Header */}
            <div className="p-3 bg-[#1f1f20] border-b border-[#333] flex items-center justify-between gap-2 shrink-0">
              <div className="relative flex-1">
                <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  ref={newTabSearchInputRef}
                  value={newTabSearch}
                  onChange={(e) => setNewTabSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') setShowNewTabSelector(false);
                    if (e.key === 'Enter') {
                      if (filteredCommandsToOpen.length > 0) {
                        handleOpenCommandInTab(filteredCommandsToOpen[0]);
                      } else if (newTabSearch.trim()) {
                        handleCreateAndOpenCommand(newTabSearch.trim());
                      }
                    }
                  }}
                  placeholder="Type to search or create command (e.g. /deposit)..."
                  className="w-full bg-[#141416] border border-[#3e3e42] focus:border-blue-500 rounded-xl pl-9 pr-3 py-2 text-xs text-white placeholder-gray-500 focus:outline-none font-mono"
                  autoFocus
                />
              </div>

              <button
                type="button"
                onClick={() => setShowNewTabSelector(false)}
                className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 cursor-pointer shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Errors tab + Create command */}
            <div className="p-2 border-b border-[#333] space-y-1.5 shrink-0">
              <button
                type="button"
                onClick={openErrorsTab}
                className={`w-full text-left px-3 py-2 rounded-xl border text-xs font-semibold flex items-center justify-between transition cursor-pointer ${
                  isErrorsTabActive
                    ? 'bg-rose-600/30 border-rose-500/50 text-rose-100'
                    : 'bg-rose-500/10 hover:bg-rose-600/25 border-rose-500/30 text-rose-200'
                }`}
              >
                <span className="flex items-center gap-2">
                  <Bug className="w-3.5 h-3.5" />
                  <span>Errors log</span>
                </span>
                <span className="text-[10px] opacity-80">Open tab</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setCreateCmdName(newTabSearch.trim());
                  setShowNewTabSelector(false);
                  setShowCreateModal(true);
                }}
                className="w-full text-left px-3 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/35 border border-emerald-500/40 text-emerald-100 text-xs font-semibold flex items-center justify-between transition cursor-pointer"
              >
                <span className="flex items-center gap-2">
                  <Plus className="w-3.5 h-3.5" />
                  <span>Create new command</span>
                </span>
                <span className="text-[10px] bg-emerald-600 text-white px-2 py-0.5 rounded font-bold">New</span>
              </button>
            </div>

            {/* Quick Create Button when typing a unique command */}
            {newTabSearch.trim() &&
              !effectiveAllCommands.some(
                (c) => c.name.toLowerCase() === newTabSearch.toLowerCase().trim()
              ) && (
                <div className="p-2 border-b border-[#333] bg-blue-500/10 shrink-0">
                  <button
                    type="button"
                    onClick={() => handleCreateAndOpenCommand(newTabSearch.trim())}
                    className="w-full text-left px-3 py-2 rounded-xl bg-blue-600/30 hover:bg-blue-600/50 border border-blue-500/40 text-blue-200 text-xs font-semibold flex items-center justify-between transition cursor-pointer"
                  >
                    <span className="font-mono truncate">
                      Create &quot;{newTabSearch.trim()}&quot;
                    </span>
                    <span className="text-[10px] bg-blue-500 text-white px-2 py-0.5 rounded font-bold shrink-0 ml-2">
                      Add Tab
                    </span>
                  </button>
                </div>
              )}

            {/* Commands List Header */}
            <div className="px-3 py-2 bg-[#202022] border-b border-[#2d2d30] flex items-center justify-between text-[11px] shrink-0">
              <span className="font-bold uppercase tracking-wider text-gray-400 text-[10px]">
                Available Commands ({filteredCommandsToOpen.length})
              </span>
              <span className="text-[10px] text-gray-500">Tap to open in editor tab</span>
            </div>

            {/* Commands List - Smooth touch scrolling across all mobile devices */}
            <div
              className="flex-1 min-h-0 overflow-y-auto overscroll-contain touch-pan-y p-2 space-y-1 scrollbar-thin"
              style={{ WebkitOverflowScrolling: 'touch' }}
            >
              {filteredCommandsToOpen.length === 0 ? (
                <div className="px-3 py-8 text-center text-xs text-gray-500">
                  No matching commands found. Press Enter or click above to create it!
                </div>
              ) : (
                filteredCommandsToOpen.map((cmd) => {
                  const b = getFileBadge(cmd.name, cmd.code);
                  const isOpen = openTabs.some((t) => t.id === cmd.id);
                  const isActive = activeTabId === cmd.id;

                  return (
                    <button
                      key={cmd.id}
                      type="button"
                      onClick={() => handleOpenCommandInTab(cmd)}
                      className={`w-full text-left px-3 py-2.5 rounded-xl text-xs flex items-center justify-between transition-colors cursor-pointer ${
                        isActive
                          ? 'bg-blue-600/20 text-blue-200 border border-blue-500/30'
                          : 'hover:bg-[#333] text-gray-300 hover:text-white border border-transparent'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <span
                          className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold shrink-0 ${
                            b === 'BMP'
                              ? 'bg-violet-500/20 text-violet-300'
                              : 'bg-sky-500/20 text-sky-300'
                          }`}
                        >
                          {b}
                        </span>
                        <span className="font-mono font-bold truncate">{cmd.name}</span>
                        {cmd.folder && cmd.folder !== 'All' && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1e1e1e] text-gray-400 shrink-0">
                            {cmd.folder}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0 ml-2">
                        {isActive ? (
                          <span className="text-[10px] text-blue-400 font-semibold">Active</span>
                        ) : isOpen ? (
                          <span className="text-[10px] text-gray-500">Open in Tab</span>
                        ) : (
                          <span className="text-[10px] text-gray-300 bg-[#1e1e20] px-2 py-0.5 rounded border border-[#3a3a3e]">
                            Open
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      {/* 8. SYNTAX CHECKER PANEL (Save / Check Syntax) */}
      <SyntaxCheckPanel
        isOpen={showSyntaxChecker}
        onClose={() => setShowSyntaxChecker(false)}
        result={syntaxResult}
        onJumpToLine={handleJumpToLine}
        commandName={activeTab?.name || '/start'}
      />

      {/* 9. DIRECT PASTE CODE MODAL (Paste Code) */}
      <PasteCodeModal
        isOpen={showPasteModal}
        onClose={() => setShowPasteModal(false)}
        onInsertCode={handleApplyPaste}
        currentCommandName={activeTab?.name || '/start'}
      />


      {/* Add New Command Modal — same as command list */}
      {showCreateModal && (
        <div className="fixed inset-0 z-[310] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-3xl p-6 shadow-2xl border border-slate-300 dark:border-slate-800 space-y-4 bg-white dark:bg-slate-900">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">Add New Command</h3>
              <button type="button" onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-slate-700 dark:hover:text-white cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              Create a new command for your bot. Enter the command name below (e.g., /start).
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const name = createCmdName.trim();
                if (!name) return;
                setShowCreateModal(false);
                handleCreateAndOpenCommand(name);
                setCreateCmdName('');
              }}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-1">Command Name</label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={createCmdName}
                  onChange={(e) => setCreateCmdName(e.target.value)}
                  placeholder="Command names like /start, /help, /settings etc."
                  className="w-full px-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2 flex-wrap">
                <button type="button" onClick={() => setShowCreateModal(false)} className="px-4 py-2 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800 cursor-pointer">
                  Cancel
                </button>
                <button type="submit" className="px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white cursor-pointer">
                  Create Command
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      
      {/* 10. EDIT COMMAND — same system as command list Edit Command */}
      {editDetailsOpen && (
        <div className="fixed inset-0 z-[310] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-3xl p-5 sm:p-6 shadow-2xl border border-slate-300 dark:border-slate-800 space-y-4 bg-white dark:bg-slate-900 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">Edit Command</h3>
              <button type="button" onClick={() => setEditDetailsOpen(false)} className="text-slate-400 hover:text-slate-700 dark:hover:text-white cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                saveEditDetails();
              }}
              className="space-y-3.5"
            >
              <div>
                <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-1.5">Command Name</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="/command"
                  className="w-full px-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-1.5">Folder</label>
                <input
                  type="text"
                  value={editFolder}
                  onChange={(e) => setEditFolder(e.target.value)}
                  placeholder="All"
                  className="w-full px-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-800 dark:text-slate-200 mb-1.5">Aliases (comma separated)</label>
                <input
                  type="text"
                  value={editAliases}
                  onChange={(e) => setEditAliases(e.target.value)}
                  placeholder="/s, start"
                  className="w-full px-3.5 py-2.5 rounded-xl text-xs bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-white font-mono focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                />
              </div>
              <div
                onClick={() => setEditPinned(!editPinned)}
                className={`p-3 rounded-2xl border transition-all cursor-pointer flex items-center justify-between ${
                  editPinned
                    ? 'bg-amber-500/10 border-amber-500/40 text-slate-900 dark:text-white'
                    : 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700/60 text-slate-700 dark:text-slate-300'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className={`w-7 h-7 rounded-xl flex items-center justify-center ${editPinned ? 'bg-amber-500 text-white' : 'bg-slate-200 dark:bg-slate-700 text-slate-500'}`}>
                    <Pin className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <span className="text-xs font-bold block">Pin Command</span>
                    <span className="text-[10px] text-slate-400 block">Keep this command at the top of the list</span>
                  </div>
                </div>
                <div className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 ${editPinned ? 'bg-amber-500' : 'bg-slate-300 dark:bg-slate-700'}`}>
                  <div className={`w-4 h-4 rounded-full bg-white transition-transform ${editPinned ? 'translate-x-4' : 'translate-x-0'}`} />
                </div>
              </div>
              <div
                onClick={() => setEditAdminOnly(!editAdminOnly)}
                className={`p-3 rounded-2xl border transition-all cursor-pointer flex items-center justify-between ${
                  editAdminOnly
                    ? 'bg-rose-500/10 border-rose-500/40 text-slate-900 dark:text-white'
                    : 'bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700/60 text-slate-700 dark:text-slate-300'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <div className={`w-7 h-7 rounded-xl flex items-center justify-center ${editAdminOnly ? 'bg-rose-600 text-white' : 'bg-slate-200 dark:bg-slate-700 text-slate-500'}`}>
                    <Shield className="w-3.5 h-3.5" />
                  </div>
                  <div>
                    <span className="text-xs font-bold block">Admin Only</span>
                    <span className="text-[10px] text-slate-400 block">Only bot administrators can execute this command</span>
                  </div>
                </div>
                <div className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 ${editAdminOnly ? 'bg-rose-600' : 'bg-slate-300 dark:bg-slate-700'}`}>
                  <div className={`w-4 h-4 rounded-full bg-white transition-transform ${editAdminOnly ? 'translate-x-4' : 'translate-x-0'}`} />
                </div>
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <button type="button" onClick={() => setEditDetailsOpen(false)} className="px-4 py-2 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800 cursor-pointer">
                  Cancel
                </button>
                <button type="submit" disabled={editSaving} className="px-4 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white cursor-pointer disabled:opacity-60">
                  {editSaving ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}


      {showHelp && (
        <div className="fixed inset-0 z-[320] flex items-center justify-center p-4 bg-black/60" onClick={() => setShowHelp(false)}>
          <div className={`w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl p-5 shadow-2xl border ${ideTheme === 'dark' ? 'bg-[#1e1e1e] border-[#333] text-gray-200' : 'bg-white border-slate-200 text-slate-800'}`} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-black flex items-center gap-2"><HelpCircle className="w-4 h-4 text-blue-500" /> Editor tools & shortcuts</h3>
              <button type="button" onClick={() => setShowHelp(false)} className="p-1 rounded-lg hover:bg-black/10 cursor-pointer"><X className="w-4 h-4" /></button>
            </div>
            <ul className="space-y-2 text-xs leading-relaxed">
              <li><b>Back</b> — Return to the command list.</li>
              <li><b>Undo / Redo</b> — Ctrl+Z / Ctrl+Y (per-tab history).</li>
              <li><b>Search</b> — Ctrl+F find in the current command.</li>
              <li><b>Format</b> — Alt+Shift+F formats Python via the server.</li>
              <li><b>Run</b> — Ctrl+Enter dry-run this command against the sandbox.</li>
              <li><b>Save</b> — Ctrl+S saves the active command code.</li>
              <li><b>Paste</b> — Paste clipboard code into the editor.</li>
              <li><b>Syntax</b> — Check syntax / unknown functions against the live catalog.</li>
              <li><b>Word wrap</b> — Toggle line wrapping.</li>
              <li><b>Theme</b> — Light / dark editor theme.</li>
              <li><b>Copy / Import / Download</b> — Clipboard, load .txt, save .txt.</li>
              <li><b>Font −/+</b> — Change editor font size.</li>
              <li><b>Edit (pencil)</b> — Same Edit Command dialog as the command list (name, folder, aliases, pin, admin).</li>
              <li><b>+</b> on the tab bar — Open another command, Errors log, or create a new command.</li>
              <li><b>Errors tab</b> — Full error log; Refresh updates it without leaving the tab.</li>
            </ul>
          </div>
        </div>
      )}

{showLeaveConfirm && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-5 shadow-2xl space-y-3">
            <h3 className="text-sm font-black text-slate-900 dark:text-white">Leave the editor?</h3>
            <p className="text-xs text-slate-500 leading-relaxed">You have changes that are not saved yet. If you leave now they stay as a draft, and you can continue from them next time.</p>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => setShowLeaveConfirm(false)} className="px-3.5 py-2 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 cursor-pointer">Stay</button>
              <button type="button" onClick={() => { setShowLeaveConfirm(false); doLeave(); }} className="px-3.5 py-2 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white cursor-pointer">Leave</button>
            </div>
          </div>
        </div>
      )}
      {pendingDraft && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 p-5 shadow-2xl space-y-3">
            <h3 className="text-sm font-black text-slate-900 dark:text-white">Continue where you left off?</h3>
            <p className="text-xs text-slate-500 leading-relaxed">This command has unsaved work from {new Date(pendingDraft.ts).toLocaleString()}. Do you want to continue from it?</p>
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={() => applyPendingDraft(false)} className="px-3.5 py-2 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 cursor-pointer">Discard it</button>
              <button type="button" onClick={() => applyPendingDraft(true)} className="px-3.5 py-2 rounded-xl text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white cursor-pointer">Yes, continue</button>
            </div>
          </div>
        </div>
      )}

      {/* Hidden file input for importing .txt files */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleUploadTxtFile}
        accept=".txt,text/plain"
        className="hidden"
      />
    </div>
  );
};
