import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webDir = path.resolve(__dirname, '..');
const backendDir = path.resolve(webDir, '../backend/wearables-bff');
const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const backendHealthUrl = process.env.WEB_DEV_BACKEND_HEALTH_URL ?? 'http://localhost:3001/api/health';

const children = [];
let shuttingDown = false;

const start = (label, cwd, args) => {
  const child = spawn(npmCmd, args, { cwd, stdio: 'inherit' });
  children.push(child);

  child.on('exit', (code, signal) => {
    if (shuttingDown) return;
    const reason = signal ? `signal ${signal}` : `code ${code ?? 0}`;
    console.error(`[dev] ${label} exited with ${reason}`);
    shutdown(code ?? 1);
  });

  return child;
};

const shutdown = (exitCode = 0) => {
  if (shuttingDown) return;
  shuttingDown = true;

  for (const child of children) {
    if (!child.killed) child.kill('SIGTERM');
  }

  setTimeout(() => {
    for (const child of children) {
      if (!child.killed) child.kill('SIGKILL');
    }
    process.exit(exitCode);
  }, 3000).unref();
};

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

const sleep = (ms) => new Promise((resolve) => {
  setTimeout(resolve, ms);
});

const isBackendReady = async () => {
  try {
    const res = await fetch(backendHealthUrl);
    return res.ok;
  } catch {
    return false;
  }
};

const waitForBackend = async (timeoutMs = 20000) => {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isBackendReady()) return true;
    await sleep(400);
  }
  return false;
};

const backendAlreadyRunning = await isBackendReady();
if (!backendAlreadyRunning) {
  start('backend', backendDir, ['run', 'dev']);
  const backendReady = await waitForBackend();
  if (!backendReady) {
    console.warn(`[dev] Backend did not report healthy at ${backendHealthUrl} before timeout`);
  }
} else {
  console.log(`[dev] Reusing running backend at ${backendHealthUrl}`);
}

start('web', webDir, ['run', 'dev:web']);
