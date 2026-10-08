import crypto from 'crypto';
import config from '../config.js';
import { databaseApiClient, type ApiTokenRecord } from '../clients/databaseApi.js';
import { getUserByEmail } from './userStore.js';

/**
 * Personal researcher tokens for the export API (/api/extraction).
 *
 * The plain token is returned once at creation; db_lord only stores its sha256
 * hash, the last characters (hint) and the owner. Tokens are revoked, never deleted.
 */

export type { ApiTokenRecord };

const TOKEN_PREFIX = 'wrt_';
const HINT_LENGTH = 4;

export const hashApiToken = (token: string): string =>
  crypto.createHash('sha256').update(token).digest('hex');

export const generateApiToken = (): string =>
  `${TOKEN_PREFIX}${crypto.randomBytes(32).toString('base64url')}`;

interface ApiTokenBackend {
  create(token: { token_hash: string; token_hint: string; owner_email: string; name: string }): Promise<ApiTokenRecord>;
  list(params: { ownerEmail?: string; includeRevoked?: boolean }): Promise<ApiTokenRecord[]>;
  verify(tokenHash: string): Promise<ApiTokenRecord | undefined>;
  revoke(tokenId: string, revokedBy: string): Promise<ApiTokenRecord>;
}

const dbLordBackend: ApiTokenBackend = {
  create: (token) => databaseApiClient.createApiToken(token),
  list: (params) => databaseApiClient.listApiTokens(params),
  verify: (tokenHash) => databaseApiClient.verifyApiToken(tokenHash),
  revoke: (tokenId, revokedBy) => databaseApiClient.revokeApiToken(tokenId, revokedBy),
};

/** USE_MOCK_DATA: keeps tokens in memory, same behaviour as db_lord. */
const createMemoryBackend = (): ApiTokenBackend => {
  const tokens = new Map<string, ApiTokenRecord & { token_hash: string }>();
  const strip = ({ token_hash: _hash, ...record }: ApiTokenRecord & { token_hash: string }) => record;
  return {
    async create(token) {
      if (Array.from(tokens.values()).some((t) => t.token_hash === token.token_hash)) {
        throw new Error('Duplicate token');
      }
      const record = {
        ...token,
        owner_email: token.owner_email.trim().toLowerCase(),
        id: crypto.randomUUID(),
        created_at: new Date().toISOString(),
        last_used_at: null,
        revoked_at: null,
        revoked_by: null,
      };
      tokens.set(record.id, record);
      return strip(record);
    },
    async list({ ownerEmail, includeRevoked }) {
      return Array.from(tokens.values())
        .filter((t) => !ownerEmail || t.owner_email === ownerEmail.trim().toLowerCase())
        .filter((t) => includeRevoked || !t.revoked_at)
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map(strip);
    },
    async verify(tokenHash) {
      const token = Array.from(tokens.values()).find((t) => t.token_hash === tokenHash && !t.revoked_at);
      if (!token) return undefined;
      token.last_used_at = new Date().toISOString();
      return strip(token);
    },
    async revoke(tokenId, revokedBy) {
      const token = tokens.get(tokenId);
      if (!token) throw new Error('Token not found');
      if (!token.revoked_at) {
        token.revoked_at = new Date().toISOString();
        token.revoked_by = revokedBy.trim().toLowerCase();
      }
      return strip(token);
    },
  };
};

const backend: ApiTokenBackend = config.useMockData ? createMemoryBackend() : dbLordBackend;

export const createApiToken = async (
  ownerEmail: string,
  name: string,
): Promise<{ token: string; record: ApiTokenRecord }> => {
  const token = generateApiToken();
  const record = await backend.create({
    token_hash: hashApiToken(token),
    token_hint: token.slice(-HINT_LENGTH),
    owner_email: ownerEmail,
    name,
  });
  return { token, record };
};

export const listApiTokens = (params: { ownerEmail?: string; includeRevoked?: boolean } = {}) =>
  backend.list(params);

export const revokeApiToken = (tokenId: string, revokedBy: string) => backend.revoke(tokenId, revokedBy);

export type ApiTokenCheck =
  | { ok: true; record: ApiTokenRecord }
  | { ok: false; status: 401 | 403; error: string };

/**
 * Checks a bearer token: it must be known and not revoked, and its owner must
 * still be an approved researcher or admin. Accounts live in memory in this
 * BFF, so after a restart the owner may be unknown until they log in again;
 * the token stays valid then (an admin can revoke it at any time).
 */
export const checkApiToken = async (token: string): Promise<ApiTokenCheck> => {
  if (!token.startsWith(TOKEN_PREFIX)) {
    return { ok: false, status: 401, error: 'Invalid API access token' };
  }
  const record = await backend.verify(hashApiToken(token));
  if (!record) {
    return { ok: false, status: 401, error: 'Invalid or revoked API access token' };
  }
  const owner = getUserByEmail(record.owner_email);
  if (owner) {
    const allowed =
      owner.status === 'approved' && (owner.isAdmin || owner.roles.includes('researcher'));
    if (!allowed) {
      return { ok: false, status: 403, error: 'Token owner no longer has researcher access' };
    }
  }
  return { ok: true, record };
};
