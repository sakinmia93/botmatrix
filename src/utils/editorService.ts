/**
 * Editor language service — everything comes from the real runtime on the server
 * (`/api/editor/catalog`, `/api/editor/validate`), so suggestions and error checks always
 * match what a bot can really run.
 *
 * Suggestion kinds (meta): local | variable | function | method | keyword | snippet |
 * builtin | library | command | object | module | constant | property | errorclass
 * Local / in-buffer symbols always score highest so they appear at the top.
 */
import { apiService } from '../services/apiService';
import type { SyntaxCheckResult, SyntaxErrorItem } from './pythonSyntaxChecker';

export interface CatalogItem { name: string; kind: string; signature?: string; doc?: string }
export interface EditorCatalog {
  globals: CatalogItem[];
  objects: Record<string, CatalogItem[]>;
  keywords: string[];
  forbidden: string[];
  modules: string[];
}

let catalogPromise: Promise<EditorCatalog | null> | null = null;
let catalogValue: EditorCatalog | null = null;

export function loadCatalog(): Promise<EditorCatalog | null> {
  if (!catalogPromise) {
    catalogPromise = apiService
      .getEditorCatalog()
      .then((c) => { catalogValue = c; return c as EditorCatalog; })
      .catch(() => { catalogPromise = null; return null; });
  }
  return catalogPromise;
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** Map catalog kind → Ace meta label the user asked for */
function metaOf(kind: string): string {
  const k = (kind || '').toLowerCase();
  if (k === 'method') return 'method';
  if (k === 'function') return 'function';
  if (k === 'keyword') return 'keyword';
  if (k === 'module' || k === 'library') return 'library';
  if (k === 'object') return 'object';
  if (k === 'property' || k === 'variable' || k === 'constant') return 'variable';
  if (k === 'command') return 'command';
  if (k === 'snippet') return 'snippet';
  if (k === 'builtin') return 'builtin';
  if (k === 'errorclass' || k === 'exception') return 'errorclass';
  if (k === 'local') return 'local';
  return kind || 'variable';
}

function toAce(item: CatalogItem, score: number, owner?: string) {
  const isFn = item.kind === 'method' || item.kind === 'function';
  const sig = item.signature && item.signature !== '(...)' ? item.signature : '';
  const meta = metaOf(item.kind);
  const doc = [
    `<b>${esc((owner ? owner + '.' : '') + item.name)}${esc(isFn ? sig || '()' : '')}</b>`,
    item.doc ? `<div style="margin-top:4px;max-width:360px;white-space:normal">${esc(item.doc)}</div>` : '',
    `<div style="margin-top:2px;opacity:.7;font-size:11px">${esc(meta)}</div>`,
  ].join('');
  return {
    caption: item.name,
    value: item.name,
    meta,
    score,
    docHTML: doc,
  };
}

/** Extract local names defined in the current buffer (assignments, def, for, except, params). */
function extractLocals(session: any, upToRow: number): { name: string; kind: string }[] {
  const found: { name: string; kind: string }[] = [];
  const seen = new Set<string>();
  const add = (name: string, kind: string) => {
    if (!name || !/^[A-Za-z_]\w*$/.test(name) || seen.has(name)) return;
    // skip pure keywords
    if (['if', 'else', 'elif', 'for', 'while', 'def', 'class', 'return', 'import', 'from', 'as', 'with', 'try', 'except', 'raise', 'pass', 'break', 'continue', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is', 'lambda'].includes(name)) return;
    seen.add(name);
    found.push({ name, kind });
  };

  const max = Math.min(upToRow + 1, session.getLength());
  for (let r = 0; r < max; r++) {
    const line: string = session.getLine(r) || '';
    // def name(
    let m = line.match(/^\s*def\s+([A-Za-z_]\w*)\s*\(/);
    if (m) add(m[1], 'function');
    // class Name
    m = line.match(/^\s*class\s+([A-Za-z_]\w*)/);
    if (m) add(m[1], 'errorclass');
    // name = ...
    const assigns = line.matchAll(/(?:^|[^.\w])([A-Za-z_]\w*)\s*=\s*[^=]/g);
    for (const a of assigns) add(a[1], 'local');
    // for x in / for x, y in
    m = line.match(/^\s*for\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s+in\s+/);
    if (m) m[1].split(',').forEach((p) => add(p.trim(), 'local'));
    // except E as name
    m = line.match(/except\s+\w+(?:\s*,\s*\w+)*\s+as\s+([A-Za-z_]\w*)/);
    if (m) add(m[1], 'local');
    // with ... as name
    m = line.match(/\bas\s+([A-Za-z_]\w*)\s*:/);
    if (m) add(m[1], 'local');
    // function params: def f(a, b=1):
    m = line.match(/def\s+\w+\s*\(([^)]*)\)/);
    if (m) {
      m[1].split(',').forEach((part) => {
        const p = part.trim().split('=')[0].trim();
        if (p && p !== 'self') add(p, 'local');
      });
    }
  }
  return found;
}

/** Common TPY snippets shown as kind=snippet */
const SNIPPETS: { caption: string; value: string; doc: string }[] = [
  { caption: 'bot.sendMessage', value: 'bot.sendMessage("text")', doc: 'Send a text message to the current chat' },
  { caption: 'Bot.saveData', value: 'Bot.saveData("key", value)', doc: 'Save bot-level data' },
  { caption: 'User.saveData', value: 'User.saveData("key", value)', doc: 'Save data for the current user' },
  { caption: 'if params', value: 'if params:\n    ', doc: 'Run only when the user sent arguments after the command' },
  { caption: 'handleNextCommand', value: 'Bot.handleNextCommand("/next")', doc: 'Wait for the next user message and run /next' },
  { caption: 'try/except', value: 'try:\n    \nexcept Exception as e:\n    bot.sendMessage(str(e))', doc: 'Catch errors inside the command' },
  { caption: 'inline keyboard', value: 'bot.sendMessage("Choose:", reply_markup={"inline_keyboard":[[{"text":"OK","callback_data":"ok"}]]})', doc: 'Send a message with an inline button' },
  { caption: 'handler pattern', value: '# Use /handler_<update_type> for special updates\n# e.g. /handler_pre_checkout_query\nbot.sendMessage(update_type)', doc: 'Special update handler template' },
];

/** Ace completer driven by the live catalog + local buffer symbols on top. */
export function createRealCompleter() {
  loadCatalog();
  return {
    identifierRegexps: [/[A-Za-z_0-9]/],
    triggerCharacters: ['.'],
    getCompletions(_editor: any, session: any, pos: { row: number; column: number }, prefix: string, callback: (e: any, r: any[]) => void) {
      const cat = catalogValue;
      if (!cat) {
        loadCatalog().then(() => callback(null, []));
        return;
      }
      const before: string = (session.getLine(pos.row) || '').slice(0, pos.column);

      // Member completion: bot. | libs.openai_lib. | message.
      const m = before.match(/([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.(\w*)$/);
      if (m) {
        const path = m[1];
        const items = cat.objects[path];
        if (!items) { callback(null, []); return; }
        callback(null, items.map((it, i) => toAce(it, 1000 - i, path)));
        return;
      }

      // Inside comment or string → no suggestions
      if (/^\s*#/.test(before) || (before.match(/["']/g) || []).length % 2 === 1) {
        callback(null, []);
        return;
      }
      if (!prefix) { callback(null, []); return; }

      const out: any[] = [];
      const pl = prefix.toLowerCase();

      // 1) LOCAL symbols from current buffer — always highest score (top of list)
      const locals = extractLocals(session, pos.row);
      for (const loc of locals) {
        if (loc.name.toLowerCase().startsWith(pl)) {
          out.push({
            caption: loc.name,
            value: loc.name,
            meta: 'local',
            score: 2000,
            docHTML: `<b>${esc(loc.name)}</b><div style="margin-top:2px;opacity:.7;font-size:11px">local ${esc(loc.kind)}</div>`,
          });
        }
      }

      // 2) Snippets
      for (const s of SNIPPETS) {
        if (s.caption.toLowerCase().includes(pl) || s.value.toLowerCase().startsWith(pl)) {
          out.push({
            caption: s.caption,
            value: s.value,
            meta: 'snippet',
            score: 1500,
            docHTML: `<b>${esc(s.caption)}</b><div style="margin-top:4px">${esc(s.doc)}</div>`,
          });
        }
      }

      // 3) Catalog globals (bot, Bot, User, message, params, libs, …)
      for (let i = 0; i < cat.globals.length; i++) {
        const g = cat.globals[i];
        if (g.name.toLowerCase().startsWith(pl)) {
          out.push(toAce(g, 900 - i));
        }
      }

      // 4) Keywords
      for (const k of cat.keywords || []) {
        if (k.toLowerCase().startsWith(pl)) {
          out.push({ caption: k, value: k, meta: 'keyword', score: 400 });
        }
      }

      // 5) Builtin / module names from catalog
      for (const mod of cat.modules || []) {
        if (mod.toLowerCase().startsWith(pl)) {
          out.push({ caption: mod, value: mod, meta: 'builtin', score: 300, docHTML: `<b>${esc(mod)}</b><div>built-in module</div>` });
        }
      }

      // 6) Command names from open tabs are added by TelebotIDE if needed (kind=command)

      callback(null, out);
    },
    getDocTooltip(item: any) {
      if (item && item.docHTML && !item.docHTML_set) item.docHTML_set = true;
    },
  };
}

/** Real validation (syntax, forbidden things, unknown functions) from the server. */
export async function validateRemote(code: string): Promise<SyntaxCheckResult> {
  const res = await apiService.validateCode(code);
  const errors: SyntaxErrorItem[] = [];
  const warnings: SyntaxErrorItem[] = [];
  for (const e of res.errors || []) {
    const item: SyntaxErrorItem = {
      line: e.line || 1,
      column: e.col || 1,
      message: e.message,
      severity: e.severity === 'warning' ? 'warning' : 'error',
    };
    (item.severity === 'warning' ? warnings : errors).push(item);
  }
  return { isValid: errors.length === 0, errors, warnings };
}
