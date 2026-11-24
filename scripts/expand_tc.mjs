import fs from 'fs';
function expand(out, parts) {
  const b64 = parts.map((p) => fs.readFileSync(p, 'utf8').trim()).join('');
  fs.writeFileSync(out, Buffer.from(b64, 'base64'));
  console.log('expanded', out, fs.statSync(out).size);
}
expand('ton_session_manager.ts', ['ton_session_manager.0.b64', 'ton_session_manager.1.b64']);
expand('server.ts', ['server.ts.0.b64', 'server.ts.1.b64']);
