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
  listAdminRequests,
  listUsersByStatus,
  normalizeUserEmail,
  requestAdminAccess,
  reviewAdminRequest,
  updateUserAccess,
  setUserStatus,
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
      role: user.role,
      status: user.status,
      adminRequestStatus: user.adminRequestStatus,
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
  const { email } = req.body;
  if (!email) {
    res.status(400).json({ error: 'Email required' });
    return;
  }
  try {
    const normalizedEmail = normalizeUserEmail(email);
    const adminEmail = isAdminEmail(normalizedEmail);
    const existingUser = getUserByEmail(normalizedEmail);
    clearAllCookies(req, res);

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

    const user = createUser(normalizedEmail, { status: 'pending', role: 'practitioner' });
    res.status(201).json({
      _id: user.id,
      status: user.status,
      message: 'Your account is awaiting admin approval.',
    });
  } catch (err) {
    logger.error('Signup error', err as Error);
    res.status(500).json({ error: 'Failed to process registration request' });
  }
});

// POST /verify-magiclink
router.get('/verify-magiclink', async (req: Request, res: Response) => {
  const { token, redirect } = req.query;
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
      const redirectPath = '/overview';
      res.redirect(frontendUrl + redirectPath);
    } else {
      res.json({
        success: true,
        user: {
          id: user.id,
          email: user.email,
          name: user.name,
          role: user.role,
          status: user.status,
          adminRequestStatus: user.adminRequestStatus,
        },
      });
    }
  } catch (err) {
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
  res.json({
    success: true,
    user: {
      id: req.user.userId,
      email: req.user.email,
      name: req.user.name,
      role: req.user.role,
      status: req.user.status,
      adminRequestStatus: req.user.adminRequestStatus,
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

  if (updated.role === 'admin') {
    res.json({
      success: true,
      message: 'You are already an admin.',
      user: {
        id: updated.id,
        email: updated.email,
        role: updated.role,
        status: updated.status,
        adminRequestStatus: updated.adminRequestStatus,
      },
    });
    return;
  }

  res.json({
    success: true,
    message:
      updated.adminRequestStatus === 'pending'
        ? 'Your admin request is pending.'
        : 'Your admin request has been submitted.',
    user: {
      id: updated.id,
      email: updated.email,
      role: updated.role,
      status: updated.status,
      adminRequestStatus: updated.adminRequestStatus,
    },
  });
});

router.get('/admin/pending-users', ...auth.adminOnly, (_req: Request, res: Response) => {
  const pendingUsers = listUsersByStatus('pending').map((user) => ({
    id: user.id,
    email: user.email,
    name: user.name,
    role: user.role,
    status: user.status,
    adminRequestStatus: user.adminRequestStatus,
    createdAt: user.createdAt.toISOString(),
  }));

  res.json({ users: pendingUsers });
});

router.get('/admin/approved-users', ...auth.adminOnly, (_req: Request, res: Response) => {
  const approvedUsers = listUsersByStatus('approved').map((user) => ({
    id: user.id,
    email: user.email,
    name: user.name,
    role: user.role,
    status: user.status,
    adminRequestStatus: user.adminRequestStatus,
    createdAt: user.createdAt.toISOString(),
  }));

  res.json({ users: approvedUsers });
});

router.get('/admin/denied-users', ...auth.adminOnly, (_req: Request, res: Response) => {
  const deniedUsers = listUsersByStatus('denied').map((user) => ({
    id: user.id,
    email: user.email,
    name: user.name,
    role: user.role,
    status: user.status,
    adminRequestStatus: user.adminRequestStatus,
    createdAt: user.createdAt.toISOString(),
    deniedAt: user.deniedAt ? user.deniedAt.toISOString() : undefined,
  }));

  res.json({ users: deniedUsers });
});

router.get('/admin/pending-admin-requests', ...auth.adminOnly, (_req: Request, res: Response) => {
  const pendingRequests = listAdminRequests('pending').map((user) => ({
    id: user.id,
    email: user.email,
    name: user.name,
    role: user.role,
    status: user.status,
    adminRequestStatus: user.adminRequestStatus,
    adminRequestedAt: user.adminRequestedAt ? user.adminRequestedAt.toISOString() : undefined,
  }));

  res.json({ users: pendingRequests });
});

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

  const isActiveAdmin = userRecord.role === 'admin' && userRecord.status === 'approved';
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
    user: {
      id: updated.id,
      email: updated.email,
      name: updated.name,
      role: updated.role,
      status: updated.status,
      adminRequestStatus: updated.adminRequestStatus,
    },
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
  const updated = reviewAdminRequest(userId, 'approved');
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  res.json({
    success: true,
    user: {
      id: updated.id,
      email: updated.email,
      name: updated.name,
      role: updated.role,
      status: updated.status,
      adminRequestStatus: updated.adminRequestStatus,
    },
  });
});

router.post('/admin/users/:userId/deny-admin', ...auth.adminOnly, (req: Request, res: Response) => {
  const { userId } = req.params;
  const updated = reviewAdminRequest(userId, 'denied');
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  res.json({
    success: true,
    user: {
      id: updated.id,
      email: updated.email,
      name: updated.name,
      role: updated.role,
      status: updated.status,
      adminRequestStatus: updated.adminRequestStatus,
    },
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

  const { role, status } = req.body as { role?: string; status?: string };
  if (!role && !status) {
    res.status(400).json({ error: 'No updates provided' });
    return;
  }

  const isValidRole = !role || role === 'admin' || role === 'practitioner';
  const isValidStatus = !status || status === 'approved' || status === 'pending' || status === 'denied';
  if (!isValidRole || !isValidStatus) {
    res.status(400).json({ error: 'Invalid role or status' });
    return;
  }

  const userRecord = getUserById(userId);
  if (!userRecord) {
    res.status(404).json({ error: 'User not found' });
    return;
  }

  const nextRole = (role as UserRecord['role'] | undefined) ?? userRecord.role;
  const nextStatus = (status as UserRecord['status'] | undefined) ?? userRecord.status;
  const isActiveAdmin = userRecord.role === 'admin' && userRecord.status === 'approved';
  const willBeActiveAdmin = nextRole === 'admin' && nextStatus === 'approved';
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
    role: role as UserRecord['role'] | undefined,
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
    user: {
      id: updated.id,
      email: updated.email,
      name: updated.name,
      role: updated.role,
      status: updated.status,
      adminRequestStatus: updated.adminRequestStatus,
    },
  });
});

router.post('/logout', (req: Request, res: Response) => {
  clearAllCookies(req, res);
  res.clearCookie('jwt', baseCookieOptions);
  res.json({ success: true });
});

export default router;
