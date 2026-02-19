import crypto from 'crypto';
import config from '../config.js';

export type NonAdminRole = 'practitioner' | 'researcher';
export type UserStatus = 'pending' | 'approved' | 'denied';
export type AccessRequestStatus = 'none' | 'pending' | 'approved' | 'denied';
export type AccessRequestType = 'admin' | NonAdminRole;

export interface UserRecord {
  id: string;
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

const usersByEmail = new Map<string, UserRecord>();
const usersById = new Map<string, UserRecord>();

const normalizeEmail = (email: string) => email.trim().toLowerCase();

const adminEmailSet = new Set(
  (config.adminEmails ?? []).map((email) => email.trim().toLowerCase()).filter(Boolean),
);

const nonAdminRoleSet = new Set<NonAdminRole>(['practitioner', 'researcher']);

const normalizeRoles = (roles: readonly NonAdminRole[]): NonAdminRole[] => {
  const deduped = Array.from(new Set(roles.filter((role) => nonAdminRoleSet.has(role))));
  return deduped.sort();
};

const userDateValue = (value?: Date) => (value ? value.getTime() : 0);

export const isAdminEmail = (email: string): boolean => adminEmailSet.has(normalizeEmail(email));

export const getUserByEmail = (email: string): UserRecord | undefined =>
  usersByEmail.get(normalizeEmail(email));

export const getUserById = (userId: string): UserRecord | undefined => usersById.get(userId);

export const listUsersByStatus = (status: UserStatus): UserRecord[] =>
  Array.from(usersByEmail.values())
    .filter((user) => user.status === status)
    .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());

export const countActiveAdmins = (): number =>
  Array.from(usersByEmail.values()).filter(
    (user) => user.isAdmin && user.status === 'approved',
  ).length;

export const createUser = (
  email: string,
  options: Partial<Pick<UserRecord, 'isAdmin' | 'roles' | 'status' | 'name'>> = {},
): UserRecord => {
  const normalizedEmail = normalizeEmail(email);
  const existing = usersByEmail.get(normalizedEmail);
  if (existing) {
    return existing;
  }

  const isAdmin = options.isAdmin ?? isAdminEmail(normalizedEmail);
  const selectedRoles = normalizeRoles(options.roles ?? ['practitioner']);
  const roles = isAdmin ? [] : selectedRoles;
  const status: UserStatus = options.status ?? (isAdmin ? 'approved' : 'pending');
  const now = new Date();
  const id = crypto.randomUUID ? crypto.randomUUID() : crypto.randomBytes(16).toString('hex');

  const user: UserRecord = {
    id,
    email: normalizedEmail,
    name: options.name,
    isAdmin,
    roles,
    status,
    adminRequestStatus: isAdmin ? 'approved' : 'none',
    adminRequestedAt: isAdmin ? now : undefined,
    adminReviewedAt: isAdmin ? now : undefined,
    roleRequestStatuses: {
      practitioner: roles.includes('practitioner') ? 'approved' : 'none',
      researcher: roles.includes('researcher') ? 'approved' : 'none',
    },
    roleRequestedAt: {},
    roleReviewedAt: {},
    createdAt: now,
    updatedAt: now,
    approvedAt: status === 'approved' ? now : undefined,
    deniedAt: status === 'denied' ? now : undefined,
  };

  usersByEmail.set(normalizedEmail, user);
  usersById.set(id, user);
  return user;
};

const markRoleApproved = (user: UserRecord, role: NonAdminRole, reviewedAt: Date) => {
  if (!user.roles.includes(role)) {
    user.roles = normalizeRoles([...user.roles, role]);
  }
  user.roleRequestStatuses[role] = 'approved';
  user.roleReviewedAt[role] = reviewedAt;
  user.roleRequestedAt[role] = user.roleRequestedAt[role] ?? reviewedAt;
};

const clearRoleAssignment = (user: UserRecord, role: NonAdminRole, reviewedAt: Date) => {
  user.roles = user.roles.filter((entry) => entry !== role);
  user.roleRequestStatuses[role] = 'none';
  user.roleRequestedAt[role] = undefined;
  user.roleReviewedAt[role] = reviewedAt;
};

const setAdminAccess = (user: UserRecord, isAdmin: boolean, changedAt: Date) => {
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

export const ensureAdminUser = (email: string): UserRecord => {
  const user = createUser(email, { isAdmin: true, status: 'approved' });
  const normalizedEmail = normalizeEmail(email);
  if (user.email !== normalizedEmail || !user.isAdmin || user.status !== 'approved') {
    const now = new Date();
    user.email = normalizedEmail;
    setAdminAccess(user, true, now);
    user.status = 'approved';
    user.updatedAt = now;
    user.approvedAt = now;
    user.deniedAt = undefined;
    usersByEmail.set(normalizedEmail, user);
  }
  return user;
};

export const setUserStatus = (userId: string, status: UserStatus): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;

  const now = new Date();
  user.status = status;
  user.updatedAt = now;
  if (status === 'approved') {
    user.approvedAt = now;
    user.deniedAt = undefined;
  } else if (status === 'denied') {
    user.deniedAt = now;
  } else {
    user.approvedAt = undefined;
    user.deniedAt = undefined;
  }
  return user;
};

export const updateUserAccess = (
  userId: string,
  updates: {
    isAdmin?: boolean;
    roles?: NonAdminRole[];
    status?: UserStatus;
  },
): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;

  let updated = false;
  const now = new Date();

  let nextIsAdmin = updates.isAdmin ?? user.isAdmin;
  let nextRoles = updates.roles ? normalizeRoles(updates.roles) : [...user.roles];

  if (nextIsAdmin) {
    nextRoles = [];
  } else if (nextRoles.length === 0) {
    nextRoles = ['practitioner'];
  }

  if (nextIsAdmin !== user.isAdmin) {
    setAdminAccess(user, nextIsAdmin, now);
    updated = true;
  }

  if (!nextIsAdmin) {
    const previousRoles = normalizeRoles(user.roles);
    const rolesChanged =
      previousRoles.length !== nextRoles.length ||
      previousRoles.some((role, index) => role !== nextRoles[index]);

    if (rolesChanged) {
      user.roles = nextRoles;
      (['practitioner', 'researcher'] as const).forEach((role) => {
        if (nextRoles.includes(role)) {
          markRoleApproved(user, role, now);
        } else if (user.roleRequestStatuses[role] === 'approved') {
          clearRoleAssignment(user, role, now);
        }
      });
      updated = true;
    }
  }

  if (updates.status && user.status !== updates.status) {
    user.status = updates.status;
    updated = true;

    if (updates.status === 'approved') {
      user.approvedAt = now;
      user.deniedAt = undefined;
    } else if (updates.status === 'denied') {
      user.deniedAt = now;
    } else {
      user.approvedAt = undefined;
      user.deniedAt = undefined;
    }
  }

  if (updated) {
    user.updatedAt = now;
  }

  return user;
};

export const listAccessRequests = (status: AccessRequestStatus): AccessRequestRecord[] =>
  Array.from(usersByEmail.values())
    .flatMap((user) => {
      const requests: AccessRequestRecord[] = [];

      if (user.adminRequestStatus === status) {
        requests.push({
          user,
          requestType: 'admin',
          status,
          requestedAt: user.adminRequestedAt,
          reviewedAt: user.adminReviewedAt,
        });
      }

      (['practitioner', 'researcher'] as const).forEach((role) => {
        if (user.roleRequestStatuses[role] === status) {
          requests.push({
            user,
            requestType: role,
            status,
            requestedAt: user.roleRequestedAt[role],
            reviewedAt: user.roleReviewedAt[role],
          });
        }
      });

      return requests;
    })
    .sort((a, b) => userDateValue(a.requestedAt) - userDateValue(b.requestedAt));

export const requestAdminAccess = (userId: string): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;
  if (user.isAdmin) {
    user.adminRequestStatus = 'approved';
    user.adminReviewedAt = new Date();
    return user;
  }

  if (user.adminRequestStatus === 'pending') {
    return user;
  }

  user.adminRequestStatus = 'pending';
  user.adminRequestedAt = new Date();
  user.adminReviewedAt = undefined;
  user.updatedAt = new Date();
  return user;
};

export const requestRoleAccess = (
  userId: string,
  role: NonAdminRole,
): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;

  if (user.isAdmin || user.roles.includes(role)) {
    user.roleRequestStatuses[role] = 'approved';
    user.roleReviewedAt[role] = new Date();
    return user;
  }

  if (user.roleRequestStatuses[role] === 'pending') {
    return user;
  }

  user.roleRequestStatuses[role] = 'pending';
  user.roleRequestedAt[role] = new Date();
  user.roleReviewedAt[role] = undefined;
  user.updatedAt = new Date();
  return user;
};

export const reviewAccessRequest = (
  userId: string,
  requestType: AccessRequestType,
  decision: 'approved' | 'denied',
): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;

  const now = new Date();
  user.updatedAt = now;

  if (requestType === 'admin') {
    user.adminRequestStatus = decision;
    user.adminReviewedAt = now;

    if (decision === 'approved') {
      setAdminAccess(user, true, now);
    }

    return user;
  }

  user.roleRequestStatuses[requestType] = decision;
  user.roleReviewedAt[requestType] = now;

  if (decision === 'approved' && !user.isAdmin) {
    markRoleApproved(user, requestType, now);
  }

  return user;
};

export const normalizeUserEmail = normalizeEmail;
