import express from 'express';
import path from 'path';
import http from 'http';
import { spawn } from 'child_process';
import { createServer as createViteServer } from 'vite';

const PORT = Number(process.env.PORT || process.env.WEB_PORT || 3000);
const PYTHON_PORT = Number(process.env.API_PORT || 5001);

let pyProcess: any = null;

function startPythonBackend() {
  console.log(`[BOT MATRIX] Starting backend on port ${PYTHON_PORT}...`);

  const isWin = process.platform === 'win32';
  const pythonCmd = process.env.PYTHON_CMD || (isWin ? 'py' : 'python3');
  const args = isWin && (pythonCmd === 'py' || pythonCmd.endsWith('py.exe'))
    ? ['-3', '-m', 'backend.server']
    : ['-m', 'backend.server'];
  pyProcess = spawn(pythonCmd, args, {
    stdio: 'inherit',
    cwd: process.cwd(),
    env: {
      ...process.env,
      API_PORT: String(PYTHON_PORT),
      PYTHONUNBUFFERED: '1',
      BEHIND_PROXY: '1',
    },
    shell: false,
    windowsHide: true,
  });

  pyProcess.on('error', (err: any) => {
    console.error('[BOT MATRIX PYTHON ERROR]:', err?.message || err);
  });

  let misses = 0;
  const wd = setInterval(() => {
    const req = http.get({ host: '127.0.0.1', port: PYTHON_PORT, path: '/api/health', timeout: 5000 }, (res) => {
      res.resume();
      misses = res.statusCode === 200 ? 0 : misses + 1;
    });
    req.on('timeout', () => req.destroy());
    req.on('error', () => { misses++; });
    if (misses >= 4) {
      console.warn('[BOT MATRIX] API not responding - restarting it');
      misses = 0;
      try { pyProcess.kill('SIGKILL'); } catch (_) {}
    }
  }, 15000);

  pyProcess.on('exit', (code: any, signal: any) => {
    clearInterval(wd);
    console.warn(`[BOT MATRIX PYTHON EXIT]: code=${code}, signal=${signal}`);
    const attempt = Number(process.env._BM_PY_RESTARTS || 0) + 1;
    process.env._BM_PY_RESTARTS = String(attempt);
    const delay = Math.min(60_000, 2000 * Math.pow(1.5, Math.min(attempt, 10)));
    console.warn(`[BOT MATRIX] Restarting Python in ${Math.round(delay / 1000)}s (attempt ${attempt})...`);
    setTimeout(startPythonBackend, delay);
  });
}

async function startServer() {
  startPythonBackend();

  const app = express();

  app.get('/health', (_req, res) => {
    res.status(200).type('text/plain').send('OK');
  });
  app.get('/healthz', (_req, res) => {
    res.status(200).json({ ok: true, service: 'bot-matrix' });
  });

  app.use(['/api', '/v2'], (req, res) => {
    const proxyOptions: http.RequestOptions = {
      hostname: '127.0.0.1',
      port: PYTHON_PORT,
      path: req.originalUrl,
      method: req.method,
      headers: (() => {
        const h: any = { ...req.headers };
        delete h['x-dm-client-ip'];
        const fwd = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
        h['x-dm-client-ip'] = fwd || req.socket.remoteAddress || '';
        h['x-forwarded-host'] = req.headers.host || '';
        h['x-forwarded-proto'] = req.headers['x-forwarded-proto'] || 'https';
        h.host = `127.0.0.1:${PYTHON_PORT}`;
        return h;
      })(),
    };

    const proxyReq = http.request(proxyOptions, (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 500, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });

    proxyReq.on('error', (err) => {
      console.warn(`[API Proxy Notice]: ${err.message}`);
      res.status(503).json({ error: 'The service is starting. Please try again in a moment.', retry: true });
    });

    req.pipe(proxyReq, { end: true });
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: {
        middlewareMode: true,
        watch: {
          ignored: [
            '**/storage/**',
            '**/*.db',
            '**/*.db-wal',
            '**/*.db-shm',
            '**/backend/**',
            '**/tests/**',
            '**/__pycache__/**',
          ],
        },
      },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath, { maxAge: '1h', index: false }));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`[BOT MATRIX] Cluster Server running on http://0.0.0.0:${PORT} (NODE_ENV=${process.env.NODE_ENV || 'development'})`);
  });
}

startServer();
