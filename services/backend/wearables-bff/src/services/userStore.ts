import config from '../config.js';
import { controlRequest, ControlApiError } from '../clients/controlApi.js';

export type NonAdminRole = 'practitioner' | 'researcher';
export type UserStatus = 'pending' | 'approved' | 'denied';
export type AccessRequestStatus = 'none' | 'pending' | 'approved' | 'denied';
export type AccessRequestType = 'admin' | NonAdminRole;

export interface UserRecord {
  id: string;
  revision: number;
  authVersion: number;
  email: string;
  name?: string;
  isAdmin: boolean;
  roles: NonAdminRole[];
  status: UserStatus;
  adminRequestStatus: AccessRequestStatus;
  adminRequestedAt?: Date;
  adminReviewedAt?: Date;
  roleRequestStatuses: Record<NonAdminRole, AccessRequestStatus>;
  roleRequestedAt: Partial<Record<NonAdminRole, Date>>;
  roleReviewedAt: Partial<Record<NonAdminRole, Date>>;
  createdAt: Date;
  updatedAt: Date;
  approvedAt?: Date;
  deniedAt?: Date;
}

export interface AccessRequestRecord {
  user: UserRecord;
  requestType: AccessRequestType;
  status: AccessRequestStatus;
  requestedAt?: Date;
  reviewedAt?: Date;
}

const normalizeEmail = (email: string) => email.trim().toLowerCase();
const normalizeRoles = (roles: readonly NonAdminRole[]): NonAdminRole[] =>
  [
    ...new Set(
      roles.filter((role) => role === 'practitioner' || role === 'researcher'),
    ),
  ].sort();
export const normalizeUserEmail = normalizeEmail;
export const isAdminEmail = (email: string) =>
  config.adminEmails.map(normalizeEmail).includes(normalizeEmail(email));

export interface UserDto {
  id: string;
  email: string;
  name?: string | null;
  is_admin: boolean;
  roles: NonAdminRole[];
  status: UserStatus;
  auth_version: number;
  revision: number;
  request_state: Record<string, any>;
  created_at: string;
  updated_at: string;
  approved_at?: string;
  denied_at?: string;
}
const date = (value?: string | null) => (value ? new Date(value) : undefined);
const dateMap = (value: Record<string, string> = {}) =>
  Object.fromEntries(Object.entries(value).map(([k, v]) => [k, date(v)]));
export const fromDto = (dto: UserDto): UserRecord => {
  if (
    !dto ||
    typeof dto.id !== 'string' ||
    !dto.id ||
    typeof dto.email !== 'string' ||
    typeof dto.is_admin !== 'boolean' ||
    !Array.isArray(dto.roles) ||
    dto.roles.some(
      (role) => role !== 'practitioner' && role !== 'researcher',
    ) ||
    !['pending', 'approved', 'denied'].includes(dto.status) ||
    !Number.isInteger(dto.auth_version) ||
    dto.auth_version < 1 ||
    !Number.isInteger(dto.revision) ||
    dto.revision < 1
  )
    throw new ControlApiError(503);
  const state = dto.request_state ?? {};
  return {
    id: dto.id,
    email: normalizeEmail(dto.email),
    name: dto.name ?? undefined,
    isAdmin: dto.is_admin,
    roles: dto.roles,
    status: dto.status,
    revision: dto.revision,
    authVersion: dto.auth_version,
    adminRequestStatus: state.adminRequestStatus ?? 'none',
    adminRequestedAt: date(state.adminRequestedAt),
    adminReviewedAt: date(state.adminReviewedAt),
    roleRequestStatuses: state.roleRequestStatuses ?? {
      practitioner: 'none',
      researcher: 'none',
    },
    roleRequestedAt: dateMap(state.roleRequestedAt),
    roleReviewedAt: dateMap(state.roleReviewedAt),
    createdAt: new Date(dto.created_at),
    updatedAt: new Date(dto.updated_at),
    approvedAt: date(dto.approved_at),
    deniedAt: date(dto.denied_at),
  };
};
const requestState = (user: UserRecord) => ({
  adminRequestStatus: user.adminRequestStatus,
  adminRequestedAt: user.adminRequestedAt,
  adminReviewedAt: user.adminReviewedAt,
  roleRequestStatuses: user.roleRequestStatuses,
  roleRequestedAt: user.roleRequestedAt,
  roleReviewedAt: user.roleReviewedAt,
});
interface UserPage {
  items: UserDto[];
  next_cursor: string | null;
}
const readPage = async (
  params: URLSearchParams,
  limit: number,
  signal?: AbortSignal,
): Promise<UserPage> => {
  params.set('limit', String(limit));
  const page = await controlRequest<UserPage>(
    `/users?${params}`,
    'GET',
    undefined,
    signal,
  );
  if (
    !page ||
    !Array.isArray(page.items) ||
    page.items.length > limit ||
    !(
      page.next_cursor === null ||
      (typeof page.next_cursor === 'string' &&
        page.next_cursor.length > 0 &&
        page.next_cursor.length <= 64)
    )
  )
    throw new ControlApiError(503);
  return page;
};
export const getUserByEmail = async (
  email: string,
  signal?: AbortSignal,
): Promise<UserRecord | undefined> => {
  const page = await readPage(
    new URLSearchParams({ email: normalizeEmail(email) }),
    1,
    signal,
  );
  // The authoritative normalized-email index is unique. Never select an arbitrary match.
  if (page.next_cursor !== null) throw new ControlApiError(503);
  if (!page.items.length) return undefined;
  const user = fromDto(page.items[0]);
  if (user.email !== normalizeEmail(email)) throw new ControlApiError(503);
  return user;
};
export const getUserById = async (
  id: string,
  signal?: AbortSignal,
): Promise<UserRecord | undefined> => {
  try {
    const user = fromDto(
      await controlRequest<UserDto>(
        `/users/${encodeURIComponent(id)}`,
        'GET',
        undefined,
        signal,
      ),
    );
    if (user.id !== id) throw new ControlApiError(503);
    return user;
  } catch (error) {
    if (error instanceof ControlApiError && error.status === 404)
      return undefined;
    throw error;
  }
};
// At most 100 pages / 10,000 records per administrative list operation.
const allUsers = async (status?: UserStatus): Promise<UserRecord[]> => {
  const users: UserRecord[] = [];
  const seen = new Set<string>();
  let after: string | undefined;
  for (let n = 0; n < 100; n++) {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (after) params.set('after', after);
    const page = await readPage(params, 100);
    users.push(...page.items.map(fromDto));
    if (page.next_cursor === null) return users;
    if (seen.has(page.next_cursor))
      throw new ControlApiError(503, 'CONTROL_LIST_LIMIT');
    seen.add(page.next_cursor);
    after = page.next_cursor;
  }
  throw new ControlApiError(503, 'CONTROL_LIST_LIMIT');
};
export const listUsersByStatus = (status: UserStatus) => allUsers(status);
export const countActiveAdmins = async () =>
  (await listUsersByStatus('approved')).filter((user) => user.isAdmin).length;
export const createUser = async (
  email: string,
  options: Partial<
    Pick<UserRecord, 'isAdmin' | 'roles' | 'status' | 'name'>
  > = {},
) =>
  fromDto(
    await controlRequest<UserDto>('/users', 'POST', {
      email: normalizeEmail(email),
      name: options.name,
      roles: normalizeRoles(options.roles ?? ['practitioner']),
    }),
  );
// Insert-only bootstrap. The database must return an existing record unchanged.
export const ensureAdminUser = async (email: string) =>
  fromDto(
    await controlRequest<UserDto>('/users/bootstrap', 'POST', {
      email: normalizeEmail(email),
    }),
  );
export const initializeUsers = async () => {
  for (const email of config.adminEmails) await ensureAdminUser(email);
};

export interface ActorIdentity {
  userId: string;
  sessionVersion: number;
  expectedRevision?: number;
}

const mutate = async (
  id: string,
  actor: ActorIdentity,
  change: (user: UserRecord) => void,
): Promise<UserRecord | undefined> => {
  const user = await getUserById(id);
  if (!user) return undefined;
  if (id !== actor.userId && !Number.isInteger(actor.expectedRevision))
    throw new ControlApiError(428, 'EXPECTED_REVISION_REQUIRED');
  if (
    actor.expectedRevision !== undefined &&
    actor.expectedRevision !== user.revision
  )
    throw new ControlApiError(409, 'STALE_REVISION');
  change(user);
  return fromDto(
    await controlRequest<UserDto>(`/users/${encodeURIComponent(id)}`, 'PATCH', {
      expected_revision: user.revision,
      actor_id: actor.userId,
      actor_auth_version: actor.sessionVersion,
      is_admin: user.isAdmin,
      roles: user.roles,
      status: user.status,
      name: user.name,
      request_state: requestState(user),
    }),
  );
};
export const revokeUserSessions = async (
  userId: string,
  expectedAuthVersion: number,
) =>
  fromDto(
    await controlRequest<UserDto>(
      `/users/${encodeURIComponent(userId)}/revoke-sessions`,
      'POST',
      {
        actor_id: userId,
        actor_auth_version: expectedAuthVersion,
        expected_auth_version: expectedAuthVersion,
      },
    ),
  );

const markRoleApproved = (
  user: UserRecord,
  role: NonAdminRole,
  reviewedAt: Date,
) => {
  if (!user.roles.includes(role)) {
    user.roles = normalizeRoles([...user.roles, role]);
  }
  user.roleRequestStatuses[role] = 'approved';
  user.roleReviewedAt[role] = reviewedAt;
  user.roleRequestedAt[role] = user.roleRequestedAt[role] ?? reviewedAt;
};

const clearRoleAssignment = (
  user: UserRecord,
  role: NonAdminRole,
  reviewedAt: Date,
) => {
  user.roles = user.roles.filter((entry) => entry !== role);
  user.roleRequestStatuses[role] = 'none';
  user.roleRequestedAt[role] = undefined;
  user.roleReviewedAt[role] = reviewedAt;
};

const setAdminAccess = (
  user: UserRecord,
  isAdmin: boolean,
  changedAt: Date,
) => {
  user.isAdmin = isAdmin;

  if (isAdmin) {
    user.roles = [];
    user.adminRequestStatus = 'approved';
    user.adminRequestedAt = user.adminRequestedAt ?? changedAt;
    user.adminReviewedAt = changedAt;
    user.roleRequestStatuses.practitioner = 'none';
    user.roleRequestStatuses.researcher = 'none';
    user.roleRequestedAt.practitioner = undefined;
    user.roleRequestedAt.researcher = undefined;
    user.roleReviewedAt.practitioner = changedAt;
    user.roleReviewedAt.researcher = changedAt;
    return;
  }

  user.adminRequestStatus = 'none';
  user.adminRequestedAt = undefined;
  user.adminReviewedAt = changedAt;
  if (user.roles.length === 0) {
    user.roles = ['practitioner'];
  }

  (['practitioner', 'researcher'] as const).forEach((role) => {
    if (user.roles.includes(role)) {
      user.roleRequestStatuses[role] = 'approved';
      user.roleRequestedAt[role] = user.roleRequestedAt[role] ?? changedAt;
      user.roleReviewedAt[role] = changedAt;
    } else {
      user.roleRequestStatuses[role] = 'none';
      user.roleRequestedAt[role] = undefined;
      user.roleReviewedAt[role] = changedAt;
    }
  });
};

export const setUserStatus = (
  id: string,
  status: UserStatus,
  actor: ActorIdentity,
) =>
  mutate(id, actor, (user) => {
    if (
      status === 'approved' &&
      user.status !== 'approved' &&
      user.roles.length === 0 &&
      !user.isAdmin
    ) {
      for (const role of ['practitioner', 'researcher'] as const)
        if (user.roleRequestStatuses[role] === 'pending')
          markRoleApproved(user, role, new Date());
    }
    user.status = status;
  });
export const updateUserAccess = (
  id: string,
  updates: { isAdmin?: boolean; roles?: NonAdminRole[]; status?: UserStatus },
  actor: ActorIdentity,
) =>
  mutate(id, actor, (user) => {
    const now = new Date();
    if (updates.isAdmin !== undefined && updates.isAdmin !== user.isAdmin)
      setAdminAccess(user, updates.isAdmin, now);
    if (!user.isAdmin && updates.roles) {
      user.roles = normalizeRoles(updates.roles);
      for (const role of ['practitioner', 'researcher'] as const) {
        if (user.roles.includes(role)) markRoleApproved(user, role, now);
        else if (user.roleRequestStatuses[role] === 'approved')
          clearRoleAssignment(user, role, now);
      }
    }
    if (updates.status) user.status = updates.status;
  });
export const requestAdminAccess = (id: string, sessionVersion: number) =>
  mutate(id, { userId: id, sessionVersion }, (user) => {
    if (user.isAdmin || user.adminRequestStatus === 'pending') return;
    user.adminRequestStatus = 'pending';
    user.adminRequestedAt = new Date();
    user.adminReviewedAt = undefined;
  });
export const requestRoleAccess = (
  id: string,
  role: NonAdminRole,
  sessionVersion: number,
) =>
  mutate(id, { userId: id, sessionVersion }, (user) => {
    if (
      user.isAdmin ||
      user.roles.includes(role) ||
      user.roleRequestStatuses[role] === 'pending'
    )
      return;
    user.roleRequestStatuses[role] = 'pending';
    user.roleRequestedAt[role] = new Date();
    user.roleReviewedAt[role] = undefined;
  });
export const reviewAccessRequest = (
  id: string,
  type: AccessRequestType,
  decision: 'approved' | 'denied',
  actor: ActorIdentity,
) =>
  mutate(id, actor, (user) => {
    const now = new Date();
    if (type === 'admin') {
      user.adminRequestStatus = decision;
      user.adminReviewedAt = now;
      if (decision === 'approved') setAdminAccess(user, true, now);
    } else {
      user.roleRequestStatuses[type] = decision;
      user.roleReviewedAt[type] = now;
      if (decision === 'approved' && !user.isAdmin)
        markRoleApproved(user, type, now);
    }
  });
export const listAccessRequests = async (
  status: AccessRequestStatus,
): Promise<AccessRequestRecord[]> =>
  (await allUsers())
    .filter((user) => user.status === 'approved')
    .flatMap((user) => {
      const records: AccessRequestRecord[] = [];
      if (user.adminRequestStatus === status)
        records.push({
          user,
          requestType: 'admin',
          status,
          requestedAt: user.adminRequestedAt,
          reviewedAt: user.adminReviewedAt,
        });
      for (const role of ['practitioner', 'researcher'] as const)
        if (user.roleRequestStatuses[role] === status)
          records.push({
            user,
            requestType: role,
            status,
            requestedAt: user.roleRequestedAt[role],
            reviewedAt: user.roleReviewedAt[role],
          });
      return records;
    })
    .sort(
      (a, b) =>
        (a.requestedAt?.getTime() ?? 0) - (b.requestedAt?.getTime() ?? 0),
    );
