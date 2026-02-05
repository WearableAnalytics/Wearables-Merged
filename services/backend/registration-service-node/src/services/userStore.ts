import crypto from 'crypto';
import config from '../config.js';

export type UserRole = 'admin' | 'user';
export type UserStatus = 'pending' | 'approved' | 'denied';

export interface UserRecord {
  id: string;
  email: string;
  name?: string;
  role: UserRole;
  status: UserStatus;
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

export const createUser = (
  email: string,
  options: Partial<Pick<UserRecord, 'role' | 'status' | 'name'>> = {},
): UserRecord => {
  const normalizedEmail = normalizeEmail(email);
  const existing = usersByEmail.get(normalizedEmail);
  if (existing) {
    return existing;
  }

  const role: UserRole = options.role ?? (isAdminEmail(normalizedEmail) ? 'admin' : 'user');
  const status: UserStatus = options.status ?? (role === 'admin' ? 'approved' : 'pending');
  const now = new Date();
  const id = crypto.randomUUID ? crypto.randomUUID() : crypto.randomBytes(16).toString('hex');
  const user: UserRecord = {
    id,
    email: normalizedEmail,
    name: options.name,
    role,
    status,
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
  user.role = role;
  user.updatedAt = new Date();
  return user;
};

export const normalizeUserEmail = normalizeEmail;
