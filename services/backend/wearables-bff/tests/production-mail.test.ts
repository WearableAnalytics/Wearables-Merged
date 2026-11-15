import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

const productionEnv = {
  PORT: '5198', NODE_ENV: 'production', API_PREFIX: '/api',
  USE_MOCK_DATA: 'false', LOG_LEVEL: 'info',
  BACKEND_URL: 'https://api.example.test',
  FRONTEND_REDIRECT_URL: 'https://app.example.test',
  FRONTEND_ORIGINS: 'https://app.example.test',
  DATABASE_API_URL: 'https://authority.example.test', DATABASE_API_TIMEOUT: '1000',
  AUTH_SESSION_EXPIRY_SECONDS: '3600', MAGIC_LINK_EXPIRY_SECONDS: '600',
  TOKEN_ISSUER: 'synthetic-production-check',
  JWT_SECRET: 'synthetic-production-signing-key-at-least-32',
  CONTROL_WRITE_TOKEN: 'synthetic-production-control-writer',
  API_TOKEN_SERVICE_TOKEN: 'synthetic-production-api-token-service',
  DATABASE_OPERATOR_TOKEN: 'synthetic-production-database-operator-32',
  ALLOW_DEV_AUTH_BYPASS: 'false', COOKIE_SECURE: 'true',
  BREVO_API_KEY: 'disabled', MAILER_FROM_NAME: '', MAILER_FROM_EMAIL: '',
  BFF_TEST_MODE: 'true',
};
Object.assign(process.env, productionEnv);

function run(script: string, changes: Record<string, string> = {}) {
  return spawnSync(process.execPath,
    ['--import', 'tsx', '--input-type=module', '-e', script],
    { env: { ...process.env, ...productionEnv, ...changes }, encoding: 'utf8' });
}

for (const key of ['', 'disabled', '   ']) {
  test(`production config starts with email disabled (${JSON.stringify(key)})`, () => {
    const result = run(`
      import assert from 'node:assert/strict';
      const { config } = await import('./src/config.ts');
      assert.equal(config.emailDeliveryEnabled, false);
      assert.equal(config.devAuthBypass, false);
      assert.equal(config.cookieSecure, true);
    `, { BREVO_API_KEY: key });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stderr, /Email sign-in is unavailable/);
    assert.doesNotMatch(result.stdout + result.stderr, /token=|synthetic-production-signing/);
  });
}

for (const [changes, error] of [
  [{ ALLOW_DEV_AUTH_BYPASS: 'true' }, /verified login and secure cookies/],
  [{ COOKIE_SECURE: 'false' }, /verified login and secure cookies/],
  [{ DATABASE_API_URL: 'http://authority.example.test' }, /authority must use HTTPS/],
  [{ CONTROL_WRITE_TOKEN: '' }, /CONTROL_WRITE_TOKEN is required/],
] as const) {
  test(`disabled email does not relax ${Object.keys(changes)[0]}`, () => {
    const result = run("await import('./src/config.ts')", changes);
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, error);
  });
}

test('disabled production login issues no proof or session and does not reveal account status', async () => {
  const { default: express } = await import('express');
  const { default: router } = await import('../src/api/routes/auth.js');
  const { auth, requireCommandOrigin } = await import('../src/middleware.js');
  const app = express();
  app.use(express.json(), requireCommandOrigin, router);
  app.get('/protected', auth.required, (_req, res) => res.json({ protected: true }));
  const server = app.listen(0, '127.0.0.1');
  await new Promise<void>((resolve) => server.once('listening', resolve));
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  const base = `http://127.0.0.1:${address.port}`;
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    assert.match(String(url), /auth-attempts$/);
    return Response.json({ allowed: true, retry_after: 0 });
  };
  try {
    for (const email of ['approved@example.test', 'unknown@example.test']) {
      const response = await originalFetch(base + '/login', {
        method: 'POST',
        headers: { Origin: productionEnv.FRONTEND_ORIGINS, 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      assert.equal(response.status, 503);
      assert.deepEqual(await response.json(), { error: 'Email sign-in is temporarily unavailable.' });
      assert.equal(response.headers.get('set-cookie'), null);
    }
    assert.equal(calls.length, 4, 'Only the client/email admission checks may run');
    assert.equal((await originalFetch(base + '/protected')).status, 401);
    const foreign = await originalFetch(base + '/login', {
      method: 'POST', headers: { Origin: 'https://foreign.example.test', 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'approved@example.test' }),
    });
    assert.equal(foreign.status, 403);
    assert.equal(calls.length, 4);
  } finally {
    globalThis.fetch = originalFetch;
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test('disabled mail sends no request and does not log its recipient or login proof', async () => {
  const { sendMagicLinkEmail, sendApprovalEmail } = await import('../src/services/mailer.js');
  const originalFetch = globalThis.fetch;
  const originalLog = console.log;
  const lines: string[] = [];
  globalThis.fetch = async () => { throw new Error('Disabled mail must not send'); };
  console.log = (line) => { lines.push(String(line)); };
  try {
    const token = 'f'.repeat(64);
    await sendMagicLinkEmail('private@example.test', token);
    await sendApprovalEmail('private@example.test');
    assert.match(lines.join('\n'), /mail.magic_link.suppressed/);
    assert.doesNotMatch(lines.join('\n'), /private@example.test|token=|f{64}/);
  } finally {
    globalThis.fetch = originalFetch;
    console.log = originalLog;
  }
});

test('configured production delivery still sends through the provider without logging the link', () => {
  const result = run(`
    import assert from 'node:assert/strict';
    let calls = 0;
    const token = 'e'.repeat(64);
    globalThis.fetch = async (url, request) => {
      calls++;
      assert.equal(url, 'https://api.brevo.com/v3/smtp/email');
      const body = JSON.parse(request.body);
      assert.equal(body.to[0].email, 'recipient@example.test');
      assert.ok(body.htmlContent.includes('token=' + token));
      return new Response('', { status: 201 });
    };
    const { sendMagicLinkEmail } = await import('./src/services/mailer.ts');
    await sendMagicLinkEmail('recipient@example.test', token);
    assert.equal(calls, 1);
  `, { BREVO_API_KEY: 'synthetic-provider-key-never-sent',
    MAILER_FROM_NAME: 'Synthetic', MAILER_FROM_EMAIL: 'sender@example.test' });
  assert.equal(result.status, 0, result.stderr);
  assert.doesNotMatch(result.stdout + result.stderr, /token=|e{64}|recipient@example.test/);
});

test('enabling delivery still requires a sender', () => {
  const result = run("await import('./src/config.ts')", { BREVO_API_KEY: 'synthetic-provider-key-never-sent' });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /MAILER_FROM_NAME is required/);
});

test('operator log mode is explicit, short-lived and automatically replaced by configured email', () => {
  for (const seconds of ['60', '900']) {
    const result = run(`
      import assert from 'node:assert/strict';
      const {config}=await import('./src/config.ts');
      assert.equal(config.operatorMagicLinkLogging, true);
      assert.equal(config.magicLinkExpirySeconds, Math.min(Number(process.env.MAGIC_LINK_EXPIRY_SECONDS),300));
      const lines=[]; console.log=(line)=>lines.push(JSON.parse(line));
      globalThis.fetch=async()=>{throw new Error('Must not send email')};
      const {sendMagicLinkEmail}=await import('./src/services/mailer.ts');
      await sendMagicLinkEmail('private@example.test','d'.repeat(64));
      assert.equal(lines.length,1);
      assert.equal(lines[0].message,'mail.magic_link.operator');
      assert.equal(lines[0].expiresInSeconds,config.magicLinkExpirySeconds);
      assert.equal(new URL(lines[0].loginUrl).searchParams.get('token'),'d'.repeat(64));
      assert.ok(!JSON.stringify(lines).includes('private@example.test'));
    `, { ALLOW_OPERATOR_MAGIC_LINK_LOGGING: 'true', LOG_LEVEL: 'error', MAGIC_LINK_EXPIRY_SECONDS: seconds });
    assert.equal(result.status, 0, result.stderr);
    assert.doesNotMatch(result.stdout, /token=|d{64}/);
  }
  const result = run(`
    import assert from 'node:assert/strict';
    const {config}=await import('./src/config.ts');
    assert.equal(config.operatorMagicLinkLogging,false);
    assert.equal(config.emailDeliveryEnabled,true);
    assert.equal(config.magicLinkExpirySeconds,600);
  `, { ALLOW_OPERATOR_MAGIC_LINK_LOGGING: 'true', BREVO_API_KEY: 'synthetic-provider-key',
    MAILER_FROM_NAME: 'Synthetic', MAILER_FROM_EMAIL: 'sender@example.test' });
  assert.equal(result.status, 0, result.stderr);
});

test('private HTTP requires an explicit flag and a Kubernetes service name', () => {
  for (const [url, flag, accepted] of [
    ['http://db-lord.db-lord.svc.cluster.local:8080', 'true', true],
    ['http://db-lord.db-lord.svc:8080', 'true', true],
    ['http://db-lord.db-lord.svc.cluster.local:8080', 'false', false],
    ['http://public.example.test', 'true', false],
    ['http://db-lord.db-lord.svc.cluster.local.attacker.test', 'true', false],
    ['http://user:pass@db-lord.db-lord.svc.cluster.local', 'true', false],
  ]) {
    const result = run("await import('./src/config.ts')", {
      DATABASE_API_URL: String(url), ALLOW_PRIVATE_AUTHORITY_HTTP: String(flag),
    });
    assert.equal(result.status === 0, accepted, String(url));
  }
});

test('operator login retains approval, hashed database proofs, rate limits and secure session checks', () => {
  const result = run(`
    import assert from 'node:assert/strict';
    import {createHash} from 'node:crypto';
    const express=(await import('express')).default;
    const router=(await import('./src/api/routes/auth.ts')).default;
    const {requireCommandOrigin}=await import('./src/middleware.ts');
    const app=express(); app.use(express.json(),requireCommandOrigin,router);
    const server=app.listen(0,'127.0.0.1');
    await new Promise(resolve=>server.once('listening',resolve));
    const base='http://127.0.0.1:'+server.address().port;
    const networkFetch=globalThis.fetch;
    let allowed=true; let challenges=[]; let logs=[]; let status='approved';
    const user={id:'01800000-0000-7000-8000-000000000001',email:'staff@example.test',
      is_admin:false,roles:['practitioner'],status:'approved',auth_version:2,revision:3,
      request_state:{},created_at:'2026-10-30T12:00:00Z',updated_at:'2026-10-30T12:00:00Z'};
    console.log=line=>logs.push(JSON.parse(line));
    globalThis.fetch=async(url,request)=>{
      const path=new URL(url);
      assert.equal(request.headers['X-Control-Service-Token'],process.env.CONTROL_WRITE_TOKEN);
      if(path.pathname.endsWith('/auth-attempts')) return Response.json({allowed,retry_after:60});
      if(path.pathname.endsWith('/users')) return Response.json({items:[{...user,status}],next_cursor:null});
      if(path.pathname.endsWith('/login-challenges')) {
        challenges.push(JSON.parse(request.body)); return Response.json({issued:true});
      }
      throw new Error('Unexpected request');
    };
    const login=()=>networkFetch(base+'/login',{method:'POST',headers:{Origin:process.env.FRONTEND_ORIGINS,
      'Content-Type':'application/json'},body:JSON.stringify({email:user.email})});
    try {
      const response=await login(); assert.equal(response.status,200);
      assert.ok(!(response.headers.get('set-cookie')??'').includes('jwt=ey'));
      const publicBody=await response.text(); assert.ok(!publicBody.includes('token='));
      assert.equal(challenges.length,1); assert.equal(logs.length,1);
      const token=new URL(logs[0].loginUrl).searchParams.get('token');
      assert.match(token,/^[0-9a-f]{64}$/);
      assert.deepEqual(challenges[0],{token_hash:createHash('sha256').update(token).digest('hex'),
        user_id:user.id,auth_version:2,ttl_seconds:300});
      assert.ok(!JSON.stringify(challenges).includes(token));
      for(status of ['pending','denied']) assert.equal((await login()).status,200);
      assert.equal(challenges.length,1); assert.equal(logs.length,1);
      allowed=false; assert.equal((await login()).status,429);
      const foreign=await networkFetch(base+'/login',{method:'POST',headers:{Origin:'https://foreign.example.test',
        'Content-Type':'application/json'},body:JSON.stringify({email:user.email})});
      assert.equal(foreign.status,403);
      assert.equal(challenges.length,1);
    } finally {
      server.closeAllConnections(); await new Promise(resolve=>server.close(resolve));
    }
  `, { ALLOW_OPERATOR_MAGIC_LINK_LOGGING: 'true', LOG_LEVEL: 'error',
    MAGIC_LINK_EXPIRY_SECONDS: '900', ALLOW_PRIVATE_AUTHORITY_HTTP: 'true',
    DATABASE_API_URL: 'http://db-lord.db-lord.svc.cluster.local:8080' });
  assert.equal(result.status, 0, result.stderr);
  assert.doesNotMatch(result.stdout, /token=|staff@example.test/);
});
