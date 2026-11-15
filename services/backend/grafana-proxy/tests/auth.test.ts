import assert from 'node:assert/strict';
import { test } from 'node:test';
import { authorizeSession } from '../src/jwtProxy.js';
import type { IncomingMessage } from 'node:http';
const originalFetch = globalThis.fetch;
const config = {
  appJwtSecret: 'synthetic-cookie-key',
  authApiUrl: 'http://127.0.0.1:5198/api/me',
};
const request = () =>
  ({ headers: { cookie: 'jwt=synthetic-session' } }) as IncomingMessage;
for (const [name, user, allowed] of [
  [
    'practitioner',
    {
      id: 'staff',
      email: 'staff@example.test',
      status: 'approved',
      isAdmin: false,
      roles: ['practitioner'],
    },
    true,
  ],
  [
    'admin',
    {
      id: 'admin',
      email: 'admin@example.test',
      status: 'approved',
      isAdmin: true,
      roles: [],
    },
    true,
  ],
  [
    'researcher',
    {
      id: 'staff',
      email: 'staff@example.test',
      status: 'approved',
      isAdmin: false,
      roles: ['researcher'],
    },
    false,
  ],
  [
    'denied',
    {
      id: 'staff',
      email: 'staff@example.test',
      status: 'denied',
      isAdmin: true,
      roles: [],
    },
    false,
  ],
  [
    'malformed roles',
    {
      id: 'staff',
      email: 'staff@example.test',
      status: 'approved',
      isAdmin: false,
      roles: 'practitioner',
    },
    false,
  ],
] as const) {
  test(`Grafana uses current account authority: ${name}`, async () => {
    globalThis.fetch = async () => Response.json({ success: true, user });
    try {
      assert.equal(Boolean(await authorizeSession(request(), config)), allowed);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
}
test('Grafana rechecks revoked authority and fails closed on an outage', async () => {
  const req = request();
  try {
    globalThis.fetch = async () =>
      Response.json({
        success: true,
        user: {
          id: 'staff',
          email: 'staff@example.test',
          status: 'approved',
          roles: ['practitioner'],
        },
      });
    assert.ok(await authorizeSession(req, config));
    globalThis.fetch = async () => new Response('', { status: 401 });
    assert.equal(await authorizeSession(req, config), null);
    globalThis.fetch = async () => {
      throw new Error('Synthetic authority outage');
    };
    assert.equal(await authorizeSession(req, config), null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Grafana WebSocket upgrades require current authority and close after revocation', async () => {
  const http = await import('node:http');
  const crypto = await import('node:crypto');
  const { spawn } = await import('node:child_process');
  let allowed = true;
  let upgrades = 0;
  const auth = http.createServer((_req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.statusCode = allowed ? 200 : 401;
    res.end(JSON.stringify({ success: true, user: { id: 'staff', email: 'staff@example.test', status: 'approved', roles: ['practitioner'] } }));
  });
  const { privateKey, publicKey } = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  let upstreamSocket;
  const upstream = http.createServer();
  upstream.on('upgrade', (req, socket) => {
    upgrades++;
    upstreamSocket = socket;
    assert.equal(req.headers.cookie, undefined);
    const { default: jwt } = requireJwt;
    assert.equal(jwt.verify(req.headers['x-jwt-assertion'] as string, publicKey, { algorithms: ['RS256'], issuer: 'wearables-grafana-proxy', audience: 'grafana' }).role, 'Viewer');
    const accept = crypto.createHash('sha1').update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
    socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n');
    upstreamSocket = socket;
  });
  const requireJwt = await import('jsonwebtoken');
  const listen = server => new Promise<number>(resolve => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
  const authPort = await listen(auth), upstreamPort = await listen(upstream);
  const reserve = http.createServer(); const port = await listen(reserve); await new Promise<void>(resolve => reserve.close(() => resolve()));
  const process = spawn(globalThis.process.execPath, ['--import', 'tsx', 'src/server.ts'], { env: { ...globalThis.process.env, NODE_ENV: 'development', PORT: String(port), AUTH_API_URL: `http://127.0.0.1:${authPort}/api/me`, GRAFANA_BASE_URL: `http://127.0.0.1:${upstreamPort}`, APP_JWT_SECRET: 'synthetic-graphana-case-token-key-32', GRAFANA_JWT_PRIVATE_KEY: privateKey.export({ type: 'pkcs8', format: 'pem' }).toString() }, stdio: 'ignore' });
  let clientSocket;
  try {
    for (let n = 0; n < 100; n++) {
      try { if ((await originalFetch(`http://127.0.0.1:${port}/health`)).ok) break; } catch {}
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    clientSocket = await new Promise<import('node:stream').Duplex>((resolve, reject) => {
      const request = http.request({ hostname: '127.0.0.1', port, path: '/grafana-proxy/api/live/ws', headers: { Cookie: 'jwt=synthetic-session', Upgrade: 'websocket', Connection: 'Upgrade', 'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': crypto.randomBytes(16).toString('base64') } });
      request.setTimeout(3000, () => request.destroy(new Error('WebSocket handshake timeout')));
      request.on('upgrade', (_res, socket) => resolve(socket)); request.on('error', reject); request.end();
    });
    assert.equal(upgrades, 1);
    allowed = false;
    await Promise.race([new Promise(resolve => clientSocket.once('close', resolve)), new Promise((_, reject) => setTimeout(() => reject(new Error('Revoked WebSocket stayed open')), 8000))]);
  } finally {
    clientSocket?.destroy(); upstreamSocket?.destroy(); process.kill('SIGTERM');
    auth.closeAllConnections(); upstream.closeAllConnections();
    await Promise.all([new Promise<void>(resolve => auth.close(() => resolve())), new Promise<void>(resolve => upstream.close(() => resolve()))]);
  }
});
