import express from 'express';
import type { CookieOptions, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import crypto from 'crypto';
import config from '../../config.js';
import { auth, parseCookies } from '../../middleware.js';
import { sendApprovalEmail, sendMagicLinkEmail } from '../../services/mailer.js';
import { logger } from '../../logger.js';
import {
  countActiveAdmins,
  createUser,
  ensureAdminUser,
  getUserByEmail,
  getUserById,
  isAdminEmail,
  listAccessRequests,
  listUsersByStatus,
  normalizeUserEmail,
  requestAdminAccess,
  requestRoleAccess,
  reviewAccessRequest,
  updateUserAccess,
  setUserStatus,
  type AccessRequestType,
  type NonAdminRole,
  type UserRecord,
  type UserStatus,
} from '../../services/userStore.js';

const router = express.Router();
const requestCookies = (req: Request) =>
  (req as Request & { cookies?: Record<string, string> }).cookies ?? parseCookies(req.headers.cookie);

const isLocalHost = (hostname: string) =>
  hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';

const parseHostnames = (raw?: string) =>
  (raw ?? '')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean)
    .map((value) => {
      try {
        return new URL(value).hostname;
      } catch {
        return undefined;
      }
    })
    .filter((value): value is string => Boolean(value));

const isLocalCookieContext = () => {
  const hostnames = [
    ...parseHostnames(process.env.FRONTEND_URL),
    ...parseHostnames(process.env.BACKEND_URL),
  ];
  return hostnames.some((hostname) => isLocalHost(hostname));
};

const resolveSecureCookies = () => {
  const explicit = process.env.COOKIE_SECURE;
  if (explicit === 'true') return true;
  if (explicit === 'false') return false;
  if (process.env.NODE_ENV === 'development') return false;
  if (isLocalCookieContext()) return false;
  return true;
};

// In-memory store for temporary EMAILAUTH tokens
const tokenStore = new Map<string, { email: string; expiresAt: Date }>();
const useSecureCookies = resolveSecureCookies();
const sameSite: CookieOptions['sameSite'] = useSecureCookies ? 'strict' : 'lax';
const baseCookieOptions: CookieOptions = {
  httpOnly: true,
  secure: useSecureCookies,
  sameSite,
  path: '/',
};

const nonAdminRoles: readonly NonAdminRole[] = ['practitioner', 'researcher'];
const nonAdminRoleSet = new Set<NonAdminRole>(nonAdminRoles);
const accessRequestTypeSet = new Set<AccessRequestType>(['admin', ...nonAdminRoles]);

const isNonAdminRole = (value: string): value is NonAdminRole =>
  nonAdminRoleSet.has(value as NonAdminRole);

const isAccessRequestType = (value: string): value is AccessRequestType =>
  accessRequestTypeSet.has(value as AccessRequestType);

const defaultRoleRequestStatuses = () => ({
  practitioner: 'none' as const,
  researcher: 'none' as const,
});

const serializeUser = (user: UserRecord) => ({
  id: user.id,
  email: user.email,
  name: user.name,
  isAdmin: user.isAdmin,
  roles: user.roles,
  status: user.status,
  adminRequestStatus: user.adminRequestStatus,
  roleRequestStatuses: user.roleRequestStatuses,
});

// Helper function to clear all cookies
const clearAllCookies = (req: Request, res: Response) => {
  const cookies = requestCookies(req);
  for (const cookie in cookies) {
    res.clearCookie(cookie, baseCookieOptions);
  }
};

// Helper function to create JWT token
const createJwtToken = (user: UserRecord) => {
  return jwt.sign(
    {
      userId: user.id,
      email: user.email,
      name: user.name,
      isAdmin: user.isAdmin,
      roles: user.roles,
      status: user.status,
      adminRequestStatus: user.adminRequestStatus,
      roleRequestStatuses: user.roleRequestStatuses,
    },
    process.env.JWT_SECRET || 'dev-secret',
    { expiresIn: '7d' },
  );
};

// Helper function to set auth cookie
const setAuthCookie = (res: Response, token: string) => {
  res.cookie('jwt', token, { ...baseCookieOptions, maxAge: 7 * 24 * 60 * 60 * 1000 });
};

// Helper function to cleanup expired tokens
const cleanupExpiredTokens = () => {
  for (const [storedToken, data] of tokenStore.entries()) {
    if (data.expiresAt < new Date()) {
      tokenStore.delete(storedToken);
    }
  }
};

// Helper function to create magic link token
const createMagicLinkToken = (email: string) => {
  const token = crypto.randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000);
  tokenStore.set(token, { email, expiresAt });
  cleanupExpiredTokens();
  return token;
};

const isMagicLinkBypass = () =>
  config.nodeEnv === 'development' || !config.mailerEnabled;

// POST /login
router.post('/login', async (req: Request, res: Response) => {
  const { email } = req.body;
  if (!email) {
    res.status(400).json({ error: 'Email required' });
    return;
  }
  try {
    const normalizedEmail = normalizeUserEmail(email);
    let existingUser = getUserByEmail(normalizedEmail);
    if (isAdminEmail(normalizedEmail)) {
      existingUser = ensureAdminUser(normalizedEmail);
    }
    clearAllCookies(req, res);
    if (!existingUser) {
      res.status(404).json({
        error: 'User not found',
        redirectToSignup: true,
        message: 'This email is not registered. Please sign up first.',
      });
      return;
    }

    if (existingUser.status === 'pending') {
      res.status(403).json({
        error: 'Account pending approval',
        message: 'Your account is awaiting admin approval.',
        code: 'PENDING_APPROVAL',
      });
      return;
    }

    if (existingUser.status === 'denied') {
      res.status(403).json({
        error: 'Account denied',
        message: 'Your access request was denied. Please contact an administrator.',
        code: 'ACCOUNT_DENIED',
      });
      return;
    }

    if (isMagicLinkBypass()) {
      const jwtToken = createJwtToken(existingUser);
      setAuthCookie(res, jwtToken);
      res.json({
        authenticated: true,
        message: 'Direct authentication successful',
        userId: existingUser.id,
      });
      return;
    }

    const token = createMagicLinkToken(existingUser.email);
    await sendMagicLinkEmail(existingUser.email, token, { isRegistration: false });
    res.json({ message: 'Magic link sent' });
  } catch (err) {
    logger.error('Magic link error', err as Error);
    res.status(500).json({ error: 'Failed to process authentication request' });
  }
});

// POST /register - Initial registration endpoint
router.post('/register', async (req: Request, res: Response) => {
  const { email, role } = req.body as { email?: string; role?: string };
  if (!email) {
    res.status(400).json({ error: 'Email required' });
    return;
  }
  try {
    const normalizedEmail = normalizeUserEmail(email);
    const adminEmail = isAdminEmail(normalizedEmail);
    const existingUser = getUserByEmail(normalizedEmail);
    clearAllCookies(req, res);

    if (!adminEmail && (!role || !isNonAdminRole(role))) {
      res.status(400).json({ error: 'A valid role is required' });
      return;
    }

    if (adminEmail) {
      const adminUser = ensureAdminUser(normalizedEmail);
      if (isMagicLinkBypass()) {
        const jwtToken = createJwtToken(adminUser);
        setAuthCookie(res, jwtToken);
        res.status(201).json({
          authenticated: true,
          message: 'Direct authentication successful',
          id: adminUser.id,
        });
      } else {
        const token = createMagicLinkToken(adminUser.email);
        await sendMagicLinkEmail(adminUser.email, token, { isRegistration: false });
        res.status(201).json({ _id: adminUser.id, message: 'Magic link sent' });
      }
      return;
    }

    if (existingUser) {
      if (existingUser.status === 'denied') {
        res.status(403).json({
          error: 'Account denied',
          message: 'Your access request was denied. Please contact an administrator.',
          code: 'ACCOUNT_DENIED',
        });
        return;
      }

      if (existingUser.status === 'pending') {
        res.status(200).json({
          message: 'Your account is awaiting admin approval.',
          status: existingUser.status,
        });
        return;
      }

      res.status(409).json({
        error: 'User already exists',
        message: 'This email is already registered. Please login instead.',
      });
      return;
    }

    const initialRole = role as NonAdminRole;
    const user = createUser(normalizedEmail, { status: 'pending', roles: [initialRole] });
    res.status(201).json({
      _id: user.id,
      status: user.status,
      requestedRole: initialRole,
      message: 'Your account is awaiting admin approval.',
    });
  } catch (err) {
    logger.error('Signup error', err as Error);
    res.status(500).json({ error: 'Failed to process registration request' });
  }
});

// POST /verify-magiclink
router.get('/verify-magiclink', async (req: Request, res: Response) => {
  const { token } = req.query;
  if (!token || typeof token !== 'string') {
    res.status(400).json({ error: 'Token required' });
    return;
  }
  try {
    clearAllCookies(req, res);
    const data = tokenStore.get(token as string);
    if (!data) {
      throw new Error('Invalid or used token');
    }
    if (data.expiresAt < new Date()) {
      tokenStore.delete(token as string);
      throw new Error('Token expired');
    }
    const email = data.email;
    tokenStore.delete(token as string);
    let user = getUserByEmail(email);
    if (isAdminEmail(email)) {
      user = ensureAdminUser(email);
    }
    if (!user) {
      throw new Error('User not found');
    }

    if (user.status !== 'approved') {
      throw new Error('User not approved');
    }

    const jwtToken = createJwtToken(user);
    setAuthCookie(res, jwtToken);

    if (process.env.NODE_ENV !== 'development') {
      const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
      const redirectPath = user.isAdmin || user.roles.includes('practitioner') ? '/overview' : '/account';
      res.redirect(frontendUrl + redirectPath);
    } else {
      res.json({
        success: true,
        user: serializeUser(user),
      });
    }
  } catch (_err) {
    // Always redirect to login page with error parameter
    const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
    res.redirect(`${frontendUrl}/error-magic_link`);
  }
});

router.get('/me', auth.required, (req: Request, res: Response) => {
  if (!req.user) {
    res.status(401).json({ error: 'Not authenticated' });
    return;
  }

  const isAdmin = Boolean(req.user.isAdmin);
  const roles = req.user.roles ?? [];
  res.json({
    success: true,
    user: {
      id: req.user.userId,
      email: req.user.email,
      name: req.user.name,
      isAdmin,
      roles,
      status: req.user.status,
      adminRequestStatus: req.user.adminRequestStatus,
      roleRequestStatuses: req.user.roleRequestStatuses ?? defaultRoleRequestStatuses(),
    },
  });
});

router.post('/request-admin', auth.required, (req: Request, res: Response) => {
  if (!req.user) {
    res.status(401).json({ error: 'Not authenticated' });
    return;
  }

  const updated = requestAdminAccess(req.user.userId);
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  if (updated.isAdmin) {
    res.json({
      success: true,
      message: 'You are already an admin.',
      user: serializeUser(updated),
    });
    return;
  }

  res.json({
    success: true,
    message:
      updated.adminRequestStatus === 'pending'
        ? 'Your admin request is pending.'
        : 'Your admin request has been submitted.',
    user: serializeUser(updated),
  });
});

router.post('/request-role', auth.required, (req: Request, res: Response) => {
  if (!req.user) {
    res.status(401).json({ error: 'Not authenticated' });
    return;
  }

  const { role } = req.body as { role?: string };
  if (!role || !isNonAdminRole(role)) {
    res.status(400).json({ error: 'A valid role is required' });
    return;
  }

  const updated = requestRoleAccess(req.user.userId, role);
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  if (updated.isAdmin || updated.roles.includes(role)) {
    res.json({
      success: true,
      message: `You already have ${role} access.`,
      user: serializeUser(updated),
    });
    return;
  }

  res.json({
    success: true,
    message:
      updated.roleRequestStatuses[role] === 'pending'
        ? `Your ${role} request is pending.`
        : `Your ${role} request has been submitted.`,
    user: serializeUser(updated),
  });
});

router.get('/admin/pending-users', ...auth.adminOnly, (_req: Request, res: Response) => {
  const pendingUsers = listUsersByStatus('pending').map((user) => ({
    ...serializeUser(user),
    createdAt: user.createdAt.toISOString(),
  }));

  res.json({ users: pendingUsers });
});

router.get('/admin/approved-users', ...auth.adminOnly, (_req: Request, res: Response) => {
  const approvedUsers = listUsersByStatus('approved').map((user) => ({
    ...serializeUser(user),
    createdAt: user.createdAt.toISOString(),
  }));

  res.json({ users: approvedUsers });
});

router.get('/admin/denied-users', ...auth.adminOnly, (_req: Request, res: Response) => {
  const deniedUsers = listUsersByStatus('denied').map((user) => ({
    ...serializeUser(user),
    createdAt: user.createdAt.toISOString(),
    deniedAt: user.deniedAt ? user.deniedAt.toISOString() : undefined,
  }));

  res.json({ users: deniedUsers });
});

const sendPendingAccessRequests = (_req: Request, res: Response) => {
  const pendingRequests = listAccessRequests('pending').map((request) => ({
    ...serializeUser(request.user),
    requestType: request.requestType,
    requestedAt: request.requestedAt ? request.requestedAt.toISOString() : undefined,
  }));

  res.json({ users: pendingRequests });
};

router.get('/admin/pending-access-requests', ...auth.adminOnly, sendPendingAccessRequests);
router.get('/admin/pending-admin-requests', ...auth.adminOnly, sendPendingAccessRequests);

const updateUserStatus = async (
  req: Request,
  res: Response,
  status: UserStatus,
) => {
  const { userId } = req.params;
  if (!userId) {
    res.status(400).json({ error: 'User ID required' });
    return;
  }

  if (req.user?.userId === userId) {
    res.status(403).json({
      error: 'Self update forbidden',
      message: 'You cannot update your own role or access.',
      code: 'SELF_UPDATE',
    });
    return;
  }

  const userRecord = getUserById(userId);
  if (!userRecord) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  const isActiveAdmin = userRecord.isAdmin && userRecord.status === 'approved';
  if (status !== 'approved' && isActiveAdmin && countActiveAdmins() <= 1) {
    res.status(409).json({
      error: 'At least one admin required',
      message: 'You must keep at least one active admin account.',
      code: 'LAST_ADMIN',
    });
    return;
  }

  const updated = setUserStatus(userId, status);
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  if (status === 'approved') {
    try {
      await sendApprovalEmail(updated.email);
    } catch (error) {
      logger.error('Failed to send approval email', error as Error);
    }
  }

  res.json({
    success: true,
    user: serializeUser(updated),
  });
};

router.post('/admin/users/:userId/approve', ...auth.adminOnly, async (req: Request, res: Response) => {
  await updateUserStatus(req, res, 'approved');
});

router.post('/admin/users/:userId/deny', ...auth.adminOnly, async (req: Request, res: Response) => {
  await updateUserStatus(req, res, 'denied');
});

router.post('/admin/users/:userId/unblock', ...auth.adminOnly, async (req: Request, res: Response) => {
  await updateUserStatus(req, res, 'pending');
});

router.post('/admin/users/:userId/approve-admin', ...auth.adminOnly, (req: Request, res: Response) => {
  const { userId } = req.params;
  const updated = reviewAccessRequest(userId, 'admin', 'approved');
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  res.json({
    success: true,
    user: serializeUser(updated),
  });
});

router.post('/admin/users/:userId/deny-admin', ...auth.adminOnly, (req: Request, res: Response) => {
  const { userId } = req.params;
  const updated = reviewAccessRequest(userId, 'admin', 'denied');
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  res.json({
    success: true,
    user: serializeUser(updated),
  });
});

const reviewRoleRequest = (
  req: Request,
  res: Response,
  decision: 'approved' | 'denied',
) => {
  const { userId } = req.params;
  if (!userId) {
    res.status(400).json({ error: 'User ID required' });
    return;
  }

  const { role } = req.body as { role?: string };
  if (!role || !isNonAdminRole(role)) {
    res.status(400).json({ error: 'A valid role is required' });
    return;
  }

  const updated = reviewAccessRequest(userId, role, decision);
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  res.json({
    success: true,
    user: serializeUser(updated),
  });
};

router.post('/admin/users/:userId/approve-role', ...auth.adminOnly, (req: Request, res: Response) => {
  reviewRoleRequest(req, res, 'approved');
});

router.post('/admin/users/:userId/deny-role', ...auth.adminOnly, (req: Request, res: Response) => {
  reviewRoleRequest(req, res, 'denied');
});

router.post('/admin/users/:userId/review-request', ...auth.adminOnly, (req: Request, res: Response) => {
  const { userId } = req.params;
  if (!userId) {
    res.status(400).json({ error: 'User ID required' });
    return;
  }

  const { requestType, decision } = req.body as { requestType?: string; decision?: string };
  if (!requestType || !isAccessRequestType(requestType)) {
    res.status(400).json({ error: 'A valid request type is required' });
    return;
  }
  if (decision !== 'approved' && decision !== 'denied') {
    res.status(400).json({ error: 'A valid decision is required' });
    return;
  }

  const updated = reviewAccessRequest(userId, requestType, decision);
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  res.json({
    success: true,
    user: serializeUser(updated),
  });
});

router.patch('/admin/users/:userId', ...auth.adminOnly, async (req: Request, res: Response) => {
  const { userId } = req.params;
  if (!userId) {
    res.status(400).json({ error: 'User ID required' });
    return;
  }

  if (req.user?.userId === userId) {
    res.status(403).json({
      error: 'Self update forbidden',
      message: 'You cannot update your own role or access.',
      code: 'SELF_UPDATE',
    });
    return;
  }

  const { roles, isAdmin, status } = req.body as {
    roles?: string[];
    isAdmin?: boolean;
    status?: string;
  };

  const userRecord = getUserById(userId);
  if (!userRecord) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  const requestedIsAdmin = typeof isAdmin === 'boolean' ? isAdmin : undefined;
  const roleListFromBody = Array.isArray(roles) ? roles : undefined;

  const normalizedRoleList = roleListFromBody
    ? Array.from(new Set(roleListFromBody))
    : undefined;

  const hasInvalidRole =
    normalizedRoleList?.some((entry) => !isNonAdminRole(entry)) ?? false;

  if (hasInvalidRole) {
    res.status(400).json({ error: 'Invalid roles' });
    return;
  }

  const typedRoles = normalizedRoleList as NonAdminRole[] | undefined;
  if (requestedIsAdmin && typedRoles && typedRoles.length > 0) {
    res.status(400).json({ error: 'Admin users cannot have non-admin roles.' });
    return;
  }

  const isValidStatus = !status || status === 'approved' || status === 'pending' || status === 'denied';
  if (!isValidStatus) {
    res.status(400).json({ error: 'Invalid status' });
    return;
  }

  if (requestedIsAdmin === undefined && !typedRoles && !status) {
    res.status(400).json({ error: 'No updates provided' });
    return;
  }

  const nextIsAdmin = requestedIsAdmin ?? userRecord.isAdmin;
  const nextRoles = nextIsAdmin ? [] : typedRoles ?? userRecord.roles;
  if (!nextIsAdmin && nextRoles.length === 0) {
    res.status(400).json({ error: 'Non-admin users must have at least one role.' });
    return;
  }

  const nextStatus = (status as UserRecord['status'] | undefined) ?? userRecord.status;
  const isActiveAdmin = userRecord.isAdmin && userRecord.status === 'approved';
  const willBeActiveAdmin = nextIsAdmin && nextStatus === 'approved';
  const activeAdmins = countActiveAdmins();

  if (isActiveAdmin && !willBeActiveAdmin && activeAdmins <= 1) {
    res.status(409).json({
      error: 'At least one admin required',
      message: 'You must keep at least one active admin account.',
      code: 'LAST_ADMIN',
    });
    return;
  }

  const previousStatus = userRecord.status;
  const updated = updateUserAccess(userId, {
    isAdmin: requestedIsAdmin,
    roles: typedRoles,
    status: status as UserRecord['status'] | undefined,
  });

  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  if (status === 'approved' && previousStatus !== 'approved') {
    try {
      await sendApprovalEmail(updated.email);
    } catch (error) {
      logger.error('Failed to send approval email', error as Error);
    }
  }

  res.json({
    success: true,
    user: serializeUser(updated),
  });
});

router.post('/logout', (req: Request, res: Response) => {
  clearAllCookies(req, res);
  res.clearCookie('jwt', baseCookieOptions);
  res.json({ success: true });
});

export default router;
