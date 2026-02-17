import crypto from 'crypto';
import config from '../config.js';

export type UserRole = 'admin' | 'practitioner';
export type UserStatus = 'pending' | 'approved' | 'denied';
export type AdminRequestStatus = 'none' | 'pending' | 'approved' | 'denied';

export interface UserRecord {
  id: string;
  email: string;
  name?: string;
  role: UserRole;
  status: UserStatus;
  adminRequestStatus: AdminRequestStatus;
  adminRequestedAt?: Date;
  adminReviewedAt?: Date;
  createdAt: Date;
  updatedAt: Date;
  approvedAt?: Date;
  deniedAt?: Date;
}

const usersByEmail = new Map<string, UserRecord>();
const usersById = new Map<string, UserRecord>();

const normalizeEmail = (email: string) => email.trim().toLowerCase();

const adminEmailSet = new Set(
  (config.adminEmails ?? []).map((email) => email.trim().toLowerCase()).filter(Boolean),
);

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
    (user) => user.role === 'admin' && user.status === 'approved',
  ).length;

export const createUser = (
  email: string,
  options: Partial<Pick<UserRecord, 'role' | 'status' | 'name'>> = {},
): UserRecord => {
  const normalizedEmail = normalizeEmail(email);
  const existing = usersByEmail.get(normalizedEmail);
  if (existing) {
    return existing;
  }

  const role: UserRole = options.role ?? (isAdminEmail(normalizedEmail) ? 'admin' : 'practitioner');
  const status: UserStatus = options.status ?? (role === 'admin' ? 'approved' : 'pending');
  const now = new Date();
  const id = crypto.randomUUID ? crypto.randomUUID() : crypto.randomBytes(16).toString('hex');
  const adminRequestStatus: AdminRequestStatus = role === 'admin' ? 'approved' : 'none';
  const user: UserRecord = {
    id,
    email: normalizedEmail,
    name: options.name,
    role,
    status,
    adminRequestStatus,
    createdAt: now,
    updatedAt: now,
    approvedAt: status === 'approved' ? now : undefined,
    deniedAt: status === 'denied' ? now : undefined,
  };

  usersByEmail.set(normalizedEmail, user);
  usersById.set(id, user);
  return user;
};

export const ensureAdminUser = (email: string): UserRecord => {
  const user = createUser(email, { role: 'admin', status: 'approved' });
  const normalizedEmail = normalizeEmail(email);
  if (user.email !== normalizedEmail || user.role !== 'admin' || user.status !== 'approved') {
    const now = new Date();
    user.email = normalizedEmail;
    user.role = 'admin';
    user.status = 'approved';
    user.adminRequestStatus = 'approved';
    user.adminReviewedAt = now;
    user.adminRequestedAt = user.adminRequestedAt ?? now;
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

export const setUserRole = (userId: string, role: UserRole): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;
  if (user.role === role) return user;
  const now = new Date();
  user.role = role;
  user.updatedAt = now;

  if (role === 'admin') {
    user.adminRequestStatus = 'approved';
    user.adminReviewedAt = now;
    user.adminRequestedAt = user.adminRequestedAt ?? now;
  } else {
    user.adminRequestStatus = 'none';
    user.adminReviewedAt = now;
    user.adminRequestedAt = undefined;
  }
  return user;
};

export const updateUserAccess = (
  userId: string,
  updates: Partial<Pick<UserRecord, 'role' | 'status'>>,
): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;

  let updated = false;
  const now = new Date();

  if (updates.role && user.role !== updates.role) {
    user.role = updates.role;
    updated = true;

    if (updates.role === 'admin') {
      user.adminRequestStatus = 'approved';
      user.adminReviewedAt = now;
      user.adminRequestedAt = user.adminRequestedAt ?? now;
    } else {
      user.adminRequestStatus = 'none';
      user.adminReviewedAt = now;
      user.adminRequestedAt = undefined;
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

const userDateValue = (value?: Date) => (value ? value.getTime() : 0);

export const listAdminRequests = (status: AdminRequestStatus): UserRecord[] =>
  Array.from(usersByEmail.values())
    .filter((user) => user.adminRequestStatus === status)
    .sort((a, b) => {
      const aTime = userDateValue(a.adminRequestedAt);
      const bTime = userDateValue(b.adminRequestedAt);
      return aTime - bTime;
    });

export const requestAdminAccess = (userId: string): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;
  if (user.role === 'admin') {
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

export const reviewAdminRequest = (
  userId: string,
  decision: 'approved' | 'denied',
): UserRecord | undefined => {
  const user = usersById.get(userId);
  if (!user) return undefined;

  const now = new Date();
  user.adminRequestStatus = decision;
  user.adminReviewedAt = now;
  user.updatedAt = now;

  if (decision === 'approved') {
    user.role = 'admin';
  }

  return user;
};

export const normalizeUserEmail = normalizeEmail;
