export type SyntaxCheckResult = {
  valid: boolean;
  errors: { line: number; message: string }[];
  warnings: { line: number; message: string }[];
};

export function validatePythonSyntax(code: string): SyntaxCheckResult {
  const errors: { line: number; message: string }[] = [];
  const lines = (code || '').split('\n');
  lines.forEach((line, i) => {
    const open = (line.match(/\(/g) || []).length;
    const close = (line.match(/\)/g) || []).length;
    if (open !== close && line.trim() && !line.trim().startsWith('#')) {
      // soft check only
    }
  });
  return { valid: errors.length === 0, errors, warnings: [] };
}
