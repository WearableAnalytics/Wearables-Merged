import express from 'express';
import type { CookieOptions, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import crypto from 'crypto';
import config from '../../config.js';
import {
  controlRequest,
  asyncRoute,
  sendControlError,
  ControlApiError,
} from '../../clients/controlApi.js';
import { auth, getUserFromRequest } from '../../middleware.js';
import {
  sendApprovalEmail,
  sendMagicLinkEmail,
} from '../../services/mailer.js';
import { logger } from '../../logger.js';
import {
  countActiveAdmins,
  revokeUserSessions,
  createUser,
  getUserByEmail,
  getUserById,
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
  fromDto,
  type UserDto,
  type UserRecord,
  type UserStatus,
} from '../../services/userStore.js';
const router = express.Router();
const isLocalHost = (hostname: string) =>
  hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
const parseHostname = (value: string): string | undefined => {
  try {
    return new URL(value).hostname;
  } catch {
    return undefined;
  }
};
const isLocalCookieContext = () => {
  const contextUrls = [
    ...config.frontendOrigins,
    config.frontendRedirectUrl,
    config.backendUrl,
  ].filter(Boolean);
  const hostnames = contextUrls
    .map((url) => parseHostname(url))
    .filter((value): value is string => Boolean(value));
  return hostnames.some((hostname) => isLocalHost(hostname));
};
const resolveSecureCookies = () => {
  if (config.cookieSecure !== undefined) return config.cookieSecure;
  if (config.isProduction) return true;
  if (config.nodeEnv === 'development') return false;
  if (isLocalCookieContext()) return false;
  return true;
};
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
const accessRequestTypeSet = new Set<AccessRequestType>([
  'admin',
  ...nonAdminRoles,
]);
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
  revision: user.revision,
  email: user.email,
  name: user.name,
  isAdmin: user.isAdmin,
  roles: user.roles,
  status: user.status,
  adminRequestStatus: user.adminRequestStatus,
  roleRequestStatuses: user.roleRequestStatuses,
});
// Helper function to clear all cookies
const clearAllCookies = (_req: Request, res: Response) => {
  res.clearCookie('jwt', baseCookieOptions);
};
// Helper function to create JWT token
const createJwtToken = (user: UserRecord, method = 'email-link-v1') =>
  jwt.sign(
    {
      type: 'web-session',
      auth_method: method,
      userId: user.id,
      email: user.email,
      sessionVersion: user.authVersion,
    },
    config.jwtSecret,
    {
      algorithm: 'HS256',
      expiresIn: config.authSessionExpirySeconds,
      issuer: config.tokenIssuer,
      audience: 'wearables-web',
      subject: user.id,
    },
  );
// Helper function to set auth cookie
const setAuthCookie = (res: Response, token: string) => {
  res.cookie('jwt', token, {
    ...baseCookieOptions,
    maxAge: config.authSessionExpirySeconds * 1000,
  });
};
// Login proofs are one-use database records, shared across BFF instances.
const tokenHash = (token: string) =>
  crypto.createHash('sha256').update(token).digest('hex');
export const createMagicLinkToken = async (email: string) => {
  const user = await getUserByEmail(email);
  if (!user || user.status !== 'approved') throw new Error('Login not allowed');
  const token = crypto.randomBytes(32).toString('hex');
  const result = await controlRequest<{ issued: boolean }>(
    '/login-challenges',
    'POST',
    {
      token_hash: tokenHash(token),
      user_id: user.id,
      auth_version: user.authVersion,
      ttl_seconds: config.magicLinkExpirySeconds,
    },
  );
  if (result?.issued !== true) throw new Error('Login proof unavailable');
  return token;
};
const authMessage =
  'If this account is approved, a sign-in link will be sent. Otherwise, register or contact an administrator.';
const registrationMessage =
  'Your registration has been received. Eligible new accounts require administrator approval; existing accounts can use sign-in.';
const validEmail = (value: unknown): value is string =>
  typeof value === 'string' &&
  value.length <= 320 &&
  /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim());
const keyHash = (value: string) =>
  crypto
    .createHmac('sha256', config.jwtSecret)
    .update('auth-limit:' + value)
    .digest('hex');
const admit = async (
  req: Request,
  res: Response,
  kind: 'login' | 'register' | 'verify',
  email?: string,
) => {
  const keys = [
    {
      kind: kind === 'verify' ? 'verify' : 'client',
      key_hash: keyHash('client:' + req.ip),
    },
    ...(email
      ? [{ kind, key_hash: keyHash('email:' + normalizeUserEmail(email)) }]
      : []),
  ];
  for (const key of keys) {
    const result = await controlRequest<{
      allowed: boolean;
      retry_after: number;
    }>('/auth-attempts', 'POST', key);
    if (
      typeof result.allowed !== 'boolean' ||
      !Number.isInteger(result.retry_after)
    )
      throw new ControlApiError(503);
    if (!result.allowed) {
      res.setHeader('Retry-After', String(result.retry_after));
      res.status(429).json({ error: 'Too many attempts. Try again later.' });
      return false;
    }
  }
  return true;
};

router.post(
  '/login',
  asyncRoute(async (req: Request, res: Response) => {
    const { email } = req.body ?? {};
    if (!validEmail(email)) {
      res.status(400).json({ error: 'Enter a valid email.' });
      return;
    }
    if (!(await admit(req, res, 'login', email))) return;
    clearAllCookies(req, res);
    const user = await getUserByEmail(email);
    if (user?.status === 'approved') {
      if (config.devAuthBypass) {
        setAuthCookie(res, createJwtToken(user, 'dev-email-v1'));
        res.json({ authenticated: true, userId: user.id });
        return;
      }
      const token = await createMagicLinkToken(user.email);
      try {
        await sendMagicLinkEmail(user.email, token);
      } catch {
        logger.error('mail.magic_link.delivery_failed');
      }
    }
    res.json({ message: authMessage });
  }),
);

router.post(
  '/register',
  asyncRoute(async (req: Request, res: Response) => {
    const { email, role } = req.body ?? {};
    if (!validEmail(email) || !isNonAdminRole(role)) {
      res
        .status(400)
        .json({ error: 'A valid email and staff role are required.' });
      return;
    }
    if (!(await admit(req, res, 'register', email))) return;
    clearAllCookies(req, res);
    // Insert-only: public registration cannot choose approval or admin authority.
    await createUser(email, { roles: [role] });
    res.status(202).json({ message: registrationMessage, status: 'pending' });
  }),
);

router.get(
  '/verify-magiclink',
  asyncRoute(async (req: Request, res: Response) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Referrer-Policy', 'no-referrer');
    if (!(await admit(req, res, 'verify'))) return;
    const token = req.query.token;
    if (typeof token !== 'string' || !/^[0-9a-f]{64}$/.test(token)) {
      res.redirect(config.frontendRedirectUrl + '/error-magic_link');
      return;
    }
    try {
      const user = fromDto(
        await controlRequest<UserDto>('/login-challenges/consume', 'POST', {
          token_hash: tokenHash(token),
        }),
      );
      if (user.status !== 'approved') throw new Error('Invalid login proof');
      clearAllCookies(req, res);
      setAuthCookie(res, createJwtToken(user));
      res.redirect(
        config.frontendRedirectUrl +
          (user.isAdmin || user.roles.includes('practitioner')
            ? '/overview'
            : '/account'),
      );
    } catch (error) {
      if (error instanceof ControlApiError && error.status >= 500) {
        sendControlError(res, error);
        return;
      }
      res.redirect(config.frontendRedirectUrl + '/error-magic_link');
    }
  }),
);

router.get(
  '/me',
  auth.required,
  asyncRoute((req: Request, res: Response) => {
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
        roleRequestStatuses:
          req.user.roleRequestStatuses ?? defaultRoleRequestStatuses(),
      },
    });
  }),
);
router.post(
  '/request-admin',
  auth.required,
  asyncRoute(async (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'Not authenticated' });
      return;
    }
    const updated = await requestAdminAccess(
      req.user.userId,
      req.user.sessionVersion,
    );
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
  }),
);
router.post(
  '/request-role',
  auth.required,
  asyncRoute(async (req: Request, res: Response) => {
    if (!req.user) {
      res.status(401).json({ error: 'Not authenticated' });
      return;
    }
    const { role } = req.body as {
      role?: string;
    };
    if (!role || !isNonAdminRole(role)) {
      res.status(400).json({ error: 'A valid role is required' });
      return;
    }
    const updated = await requestRoleAccess(
      req.user.userId,
      role,
      req.user.sessionVersion,
    );
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
  }),
);
router.get(
  '/admin/pending-users',
  ...auth.adminOnly,
  asyncRoute(async (_req: Request, res: Response) => {
    const pendingUsers = (await listUsersByStatus('pending')).map((user) => ({
      ...serializeUser(user),
      createdAt: user.createdAt.toISOString(),
    }));
    res.json({ users: pendingUsers });
  }),
);
router.get(
  '/admin/approved-users',
  ...auth.adminOnly,
  asyncRoute(async (_req: Request, res: Response) => {
    const approvedUsers = (await listUsersByStatus('approved')).map((user) => ({
      ...serializeUser(user),
      createdAt: user.createdAt.toISOString(),
    }));
    res.json({ users: approvedUsers });
  }),
);
router.get(
  '/admin/denied-users',
  ...auth.adminOnly,
  asyncRoute(async (_req: Request, res: Response) => {
    const deniedUsers = (await listUsersByStatus('denied')).map((user) => ({
      ...serializeUser(user),
      createdAt: user.createdAt.toISOString(),
      deniedAt: user.deniedAt ? user.deniedAt.toISOString() : undefined,
    }));
    res.json({ users: deniedUsers });
  }),
);
const sendPendingAccessRequests = async (_req: Request, res: Response) => {
  const pendingRequests = (await listAccessRequests('pending')).map(
    (request) => ({
      ...serializeUser(request.user),
      requestType: request.requestType,
      requestedAt: request.requestedAt
        ? request.requestedAt.toISOString()
        : undefined,
    }),
  );
  res.json({ users: pendingRequests });
};
router.get(
  '/admin/pending-access-requests',
  ...auth.adminOnly,
  asyncRoute(sendPendingAccessRequests),
);
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
  const userRecord = await getUserById(userId);
  if (!userRecord) {
    res.status(404).json({ error: 'User not found' });
    return;
  }
  const isActiveAdmin = userRecord.isAdmin && userRecord.status === 'approved';
  if (
    status !== 'approved' &&
    isActiveAdmin &&
    (await countActiveAdmins()) <= 1
  ) {
    res.status(409).json({
      error: 'At least one admin required',
      message: 'You must keep at least one active admin account.',
      code: 'LAST_ADMIN',
    });
    return;
  }
  const updated = await setUserStatus(userId, status, {
    ...req.user!,
    expectedRevision: req.body?.expectedRevision,
  });
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }
  if (status === 'approved') {
    try {
      await sendApprovalEmail(updated.email);
    } catch (error) {
      logger.error('mail.approval.failed');
    }
  }
  res.json({
    success: true,
    user: serializeUser(updated),
  });
};
router.post(
  '/admin/users/:userId/approve',
  ...auth.adminOnly,
  asyncRoute(async (req: Request, res: Response) => {
    await updateUserStatus(req, res, 'approved');
  }),
);
router.post(
  '/admin/users/:userId/deny',
  ...auth.adminOnly,
  asyncRoute(async (req: Request, res: Response) => {
    await updateUserStatus(req, res, 'denied');
  }),
);
router.post(
  '/admin/users/:userId/unblock',
  ...auth.adminOnly,
  asyncRoute(async (req: Request, res: Response) => {
    await updateUserStatus(req, res, 'pending');
  }),
);
router.post(
  '/admin/users/:userId/approve-admin',
  ...auth.adminOnly,
  asyncRoute(async (req: Request, res: Response) => {
    const { userId } = req.params;
    const updated = await reviewAccessRequest(userId, 'admin', 'approved', {
      ...req.user!,
      expectedRevision: req.body?.expectedRevision,
    });
    if (!updated) {
      res.status(404).json({ error: 'User not found' });
      return;
    }
    res.json({
      success: true,
      user: serializeUser(updated),
    });
  }),
);
router.post(
  '/admin/users/:userId/deny-admin',
  ...auth.adminOnly,
  asyncRoute(async (req: Request, res: Response) => {
    const { userId } = req.params;
    const updated = await reviewAccessRequest(userId, 'admin', 'denied', {
      ...req.user!,
      expectedRevision: req.body?.expectedRevision,
    });
    if (!updated) {
      res.status(404).json({ error: 'User not found' });
      return;
    }
    res.json({
      success: true,
      user: serializeUser(updated),
    });
  }),
);
const reviewRoleRequest = async (
  req: Request,
  res: Response,
  decision: 'approved' | 'denied',
) => {
  const { userId } = req.params;
  if (!userId) {
    res.status(400).json({ error: 'User ID required' });
    return;
  }
  const { role } = req.body as {
    role?: string;
  };
  if (!role || !isNonAdminRole(role)) {
    res.status(400).json({ error: 'A valid role is required' });
    return;
  }
  const updated = await reviewAccessRequest(userId, role, decision, {
    ...req.user!,
    expectedRevision: req.body?.expectedRevision,
  });
  if (!updated) {
    res.status(404).json({ error: 'User not found' });
    return;
  }
  res.json({
    success: true,
    user: serializeUser(updated),
  });
};
router.post(
  '/admin/users/:userId/approve-role',
  ...auth.adminOnly,
  asyncRoute((req: Request, res: Response) => {
    return reviewRoleRequest(req, res, 'approved');
  }),
);
router.post(
  '/admin/users/:userId/deny-role',
  ...auth.adminOnly,
  asyncRoute((req: Request, res: Response) => {
    return reviewRoleRequest(req, res, 'denied');
  }),
);
router.post(
  '/admin/users/:userId/review-request',
  ...auth.adminOnly,
  asyncRoute(async (req: Request, res: Response) => {
    const { userId } = req.params;
    if (!userId) {
      res.status(400).json({ error: 'User ID required' });
      return;
    }
    const { requestType, decision } = req.body as {
      requestType?: string;
      decision?: string;
    };
    if (!requestType || !isAccessRequestType(requestType)) {
      res.status(400).json({ error: 'A valid request type is required' });
      return;
    }
    if (decision !== 'approved' && decision !== 'denied') {
      res.status(400).json({ error: 'A valid decision is required' });
      return;
    }
    const updated = await reviewAccessRequest(userId, requestType, decision, {
      ...req.user!,
      expectedRevision: req.body?.expectedRevision,
    });
    if (!updated) {
      res.status(404).json({ error: 'User not found' });
      return;
    }
    res.json({
      success: true,
      user: serializeUser(updated),
    });
  }),
);
router.patch(
  '/admin/users/:userId',
  ...auth.adminOnly,
  asyncRoute(async (req: Request, res: Response) => {
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
    const userRecord = await getUserById(userId);
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
      res
        .status(400)
        .json({ error: 'Admin users cannot have non-admin roles.' });
      return;
    }
    const isValidStatus =
      !status ||
      status === 'approved' ||
      status === 'pending' ||
      status === 'denied';
    if (!isValidStatus) {
      res.status(400).json({ error: 'Invalid status' });
      return;
    }
    if (requestedIsAdmin === undefined && !typedRoles && !status) {
      res.status(400).json({ error: 'No updates provided' });
      return;
    }
    const nextIsAdmin = requestedIsAdmin ?? userRecord.isAdmin;
    const nextRoles = nextIsAdmin ? [] : (typedRoles ?? userRecord.roles);
    if (!nextIsAdmin && nextRoles.length === 0) {
      res
        .status(400)
        .json({ error: 'Non-admin users must have at least one role.' });
      return;
    }
    const nextStatus =
      (status as UserRecord['status'] | undefined) ?? userRecord.status;
    const isActiveAdmin =
      userRecord.isAdmin && userRecord.status === 'approved';
    const willBeActiveAdmin = nextIsAdmin && nextStatus === 'approved';
    const activeAdmins = await countActiveAdmins();
    if (isActiveAdmin && !willBeActiveAdmin && activeAdmins <= 1) {
      res.status(409).json({
        error: 'At least one admin required',
        message: 'You must keep at least one active admin account.',
        code: 'LAST_ADMIN',
      });
      return;
    }
    const previousStatus = userRecord.status;
    const updated = await updateUserAccess(
      userId,
      {
        isAdmin: requestedIsAdmin,
        roles: typedRoles,
        status: status as UserRecord['status'] | undefined,
      },
      { ...req.user!, expectedRevision: req.body?.expectedRevision },
    );
    if (!updated) {
      res.status(404).json({ error: 'User not found' });
      return;
    }
    if (status === 'approved' && previousStatus !== 'approved') {
      try {
        await sendApprovalEmail(updated.email);
      } catch (error) {
        logger.error('mail.approval.failed');
      }
    }
    res.json({
      success: true,
      user: serializeUser(updated),
    });
  }),
);
router.post(
  '/logout',
  asyncRoute(async (req: Request, res: Response) => {
    const user = await getUserFromRequest(req);
    if (user) await revokeUserSessions(user.userId, user.sessionVersion);
    clearAllCookies(req, res);
    res.clearCookie('jwt', baseCookieOptions);
    res.json({ success: true });
  }),
);
export default router;
