import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import jwt from 'jsonwebtoken';
import {
  PatientFromJSON,
  PatientToJSON,
} from '../src/api/openapi-client/models/Patient.js';
import {
  PatientFromJSON as WebPatientFromJSON,
  PatientToJSON as WebPatientToJSON,
} from '../../../web/src/api/openapi-client/models/Patient.ts';

Object.assign(process.env, {
  PORT: '5198',
  NODE_ENV: 'development',
  API_PREFIX: '/api',
  USE_MOCK_DATA: 'false',
  LOG_LEVEL: 'error',
  BACKEND_URL: 'http://127.0.0.1:5198',
  FRONTEND_REDIRECT_URL: 'http://127.0.0.1:5199',
  FRONTEND_ORIGINS: 'http://127.0.0.1:5199',
  DATABASE_API_URL: 'http://127.0.0.1:5197',
  DATABASE_API_TIMEOUT: '1000',
  AUTH_SESSION_EXPIRY_SECONDS: '3600',
  MAGIC_LINK_EXPIRY_SECONDS: '600',
  TOKEN_ISSUER: 'synthetic-account-unit',
  JWT_SECRET: 'synthetic-account-unit-signing-key-at-least-32',
  CONTROL_WRITE_TOKEN: 'synthetic-account-unit-writer',
  API_TOKEN_SERVICE_TOKEN: 'synthetic-account-unit-token-service',
  DATABASE_OPERATOR_TOKEN: 'synthetic-account-unit-database-operator-32',
  BFF_TEST_MODE: 'true',
  ALLOW_DEV_AUTH_BYPASS: 'false',
});
const { getUserFromRequest, requireCommandOrigin } = await import(
  '../src/middleware.js'
);
const { ControlApiError } = await import('../src/clients/controlApi.js');
const id = '01800000-0000-7000-8000-000000000001';
const user = {
  id,
  email: 'staff@example.test',
  is_admin: false,
  roles: ['practitioner'],
  status: 'approved',
  auth_version: 2,
  revision: 3,
  request_state: {},
  created_at: '2026-10-30T12:00:00Z',
  updated_at: '2026-10-30T12:00:00Z',
};
const originalFetch = globalThis.fetch;
const cookie = (claims = {}, options = {}) =>
  jwt.sign(
    {
      type: 'web-session',
      auth_method: 'email-link-v1',
      userId: id,
      email: user.email,
      sessionVersion: 2,
      ...claims,
    },
    process.env.JWT_SECRET!,
    {
      algorithm: 'HS256',
      issuer: process.env.TOKEN_ISSUER,
      audience: 'wearables-web',
      subject: id,
      expiresIn: 600,
      ...options,
    },
  );
const request = (value: string) =>
  ({ headers: { cookie: `jwt=${value}` } }) as any;

for (const [name, parse, serialize] of [
  ['BFF', PatientFromJSON, PatientToJSON],
  ['web', WebPatientFromJSON, WebPatientToJSON],
] as const) {
  test(`${name}: unknown patient DOB remains null through generated JSON conversion`, () => {
    const value = parse({
      patientId: id,
      firstName: 'Synthetic',
      lastName: 'Person',
      birthDate: null,
    });
    assert.equal(value.birthDate, null);
    assert.equal(serialize(value).birthDate, null);
    const known = parse({
      patientId: id,
      firstName: 'Synthetic',
      lastName: 'Person',
      birthDate: '1980-01-01',
    });
    assert.equal(serialize(known).birthDate, '1980-01-01');
  });
}
test('session authority comes from the stored account, not JWT role claims', async () => {
  globalThis.fetch = async () => Response.json(user);
  try {
    const result = await getUserFromRequest(
      request(cookie({ isAdmin: true, roles: ['researcher'] })),
    );
    assert.equal(result?.isAdmin, false);
    assert.deepEqual(result?.roles, ['practitioner']);
    assert.equal(result?.sessionVersion, 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('revoked version, wrong account and wrong audience cannot reuse a session', async () => {
  globalThis.fetch = async () => Response.json(user);
  try {
    for (const token of [
      cookie({ sessionVersion: 1 }),
      cookie({ auth_method: undefined }),
      cookie({ auth_method: 'email-link' }),
      cookie({ email: 'other@example.test' }),
      cookie({}, { audience: 'wearables-mobile' }),
      cookie({ type: 'case-verification' }),
      cookie({}, { issuer: 'foreign' }),
      cookie({}, { expiresIn: -1 }),
    ]) {
      assert.equal(await getUserFromRequest(request(token)), undefined);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});
test('authority outage and malformed authority fail closed, without cached acceptance', async () => {
  try {
    globalThis.fetch = async () => Response.json(user);
    assert.ok(await getUserFromRequest(request(cookie())));
    globalThis.fetch = async () => {
      throw new Error('synthetic private upstream error');
    };
    await assert.rejects(
      getUserFromRequest(request(cookie())),
      (error: any) =>
        error instanceof ControlApiError &&
        error.status === 503 &&
        !error.message.includes('private'),
    );
    globalThis.fetch = async () =>
      Response.json({ ...user, roles: ['unrecognized-admin'] });
    await assert.rejects(
      getUserFromRequest(request(cookie())),
      ControlApiError,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
test('malformed cookie and legacy untyped JWT do not authenticate', async () => {
  assert.equal(await getUserFromRequest(request('%zz')), undefined);
  assert.equal(
    await getUserFromRequest(
      request(
        jwt.sign({ userId: id, email: user.email }, process.env.JWT_SECRET!),
      ),
    ),
    undefined,
  );
});
test('cookie commands require an exact approved Origin; reads still work', () => {
  for (const [method, origin, allowed] of [
    ['POST', 'http://127.0.0.1:5199', true],
    ['PUT', 'http://127.0.0.1:5199/foreign', false],
    ['POST', 'https://foreign.example.test', false],
    ['POST', undefined, false],
    ['GET', undefined, true],
  ] as const) {
    let next = false,
      status = 200;
    const res: any = {
      status(value: number) {
        status = value;
        return this;
      },
      json() {
        return this;
      },
    };
    requireCommandOrigin({ method, headers: { origin } } as any, res, () => {
      next = true;
    });
    assert.equal(next, allowed);
    assert.equal(status, allowed ? 200 : 403);
  }
});

test('development email bypass is rejected for a non-loopback origin', () => {
  const result = spawnSync(
    process.execPath,
    ['--import', 'tsx', '-e', "import('./src/config.ts')"],
    {
      env: {
        ...process.env,
        ALLOW_DEV_AUTH_BYPASS: 'true',
        FRONTEND_ORIGINS: 'https://example.test',
      },
      encoding: 'utf8',
    },
  );
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /ALLOW_DEV_AUTH_BYPASS|loopback/);
});
test('production rejects plaintext account-authority transport', () => {
  const result = spawnSync(
    process.execPath,
    ['--import', 'tsx', '-e', "import('./src/config.ts')"],
    {
      env: {
        ...process.env,
        NODE_ENV: 'production',
        MAILER_FROM_NAME: 'Synthetic',
        MAILER_FROM_EMAIL: 'sender@example.test',
        BREVO_API_KEY: 'synthetic-no-send-key',
        ALLOW_DEV_AUTH_BYPASS: 'false',
        BACKEND_URL: 'https://api.example.test',
        FRONTEND_REDIRECT_URL: 'https://app.example.test',
        FRONTEND_ORIGINS: 'https://app.example.test',
      },
      encoding: 'utf8',
    },
  );
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Production account authority must use HTTPS/);
});

test('public login uses the shared admission check before any account lookup', async () => {
  const { default: express } = await import('express');
  const { default: router } = await import('../src/api/routes/auth.js');
  const app = express();
  app.use(express.json(), requireCommandOrigin, router);
  const server = app.listen(0, '127.0.0.1');
  await new Promise<void>((resolve) => server.once('listening', resolve));
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  let requests = 0;
  globalThis.fetch = async () => {
    requests++;
    return Response.json({ allowed: false, retry_after: 42 });
  };
  try {
    const response = await originalFetch(
      `http://127.0.0.1:${address.port}/login`,
      {
        method: 'POST',
        headers: {
          Origin: process.env.FRONTEND_REDIRECT_URL!,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: 'staff@example.test' }),
      },
    );
    assert.equal(response.status, 429);
    assert.equal(response.headers.get('retry-after'), '42');
    assert.equal(requests, 1);
  } finally {
    globalThis.fetch = originalFetch;
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
