import type { JwtPayload } from '../middleware.js';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const isUuid = (value: unknown): value is string =>
  typeof value === 'string' && UUID.test(value) && value !== '00000000-0000-0000-0000-000000000000';

export const actor = (user: JwtPayload) => ({ actor_id: user.userId, actor_auth_version: user.sessionVersion });
export const actorQuery = (user: JwtPayload) => new URLSearchParams({
  actor_id: user.userId, actor_auth_version: String(user.sessionVersion),
}).toString();
