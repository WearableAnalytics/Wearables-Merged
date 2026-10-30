import express from 'express';
import type { CookieOptions, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import config from '../../config.js';
import { controlRequest, asyncRoute, ControlApiError } from '../../clients/controlApi.js';
import { auth, getUserFromRequest, parseCookies, type JwtPayload } from '../../middleware.js';
import {
  countActiveAdmins,
  revokeUserSessions,
  getUserById,
  listAccessRequests,
  listUsersByStatus,
  reviewAccessRequest,
  updateUserAccess,
  setUserStatus,
  fromDto,
  type UserDto,
  type UserRecord,
  type UserStatus,
  type AccessRequestType,
  type NonAdminRole,
} from '../../services/userStore.js';

const router = express.Router();
const baseCookieOptions: CookieOptions = {
  httpOnly: true,
  secure: config.isProduction || config.cookieSecure === true,
  sameSite: config.isProduction || config.cookieSecure === true ? 'strict' : 'lax',
  path: '/',
};
const clearAllCookies = (_req: Request, res: Response) => {
  res.clearCookie('jwt', baseCookieOptions);
  res.clearCookie('password_setup', baseCookieOptions);
};
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
const nonAdminRoles: readonly NonAdminRole[] = ['practitioner', 'researcher'];
const isNonAdminRole = (value: string): value is NonAdminRole =>
  nonAdminRoles.includes(value as NonAdminRole);
const isAccessRequestType = (value: string): value is AccessRequestType =>
  value === 'admin' || isNonAdminRole(value);
const defaultRoleRequestStatuses = () => ({
  practitioner: 'none' as const,
  researcher: 'none' as const,
});
const issueSession = (res: Response, user: UserRecord, initial = false) => {
  const expiry = initial ? 600 : config.authSessionExpirySeconds;
  const token = jwt.sign(
    {
      auth_method: 'password-v1',
      type: initial ? 'password-setup' : 'web-session',
      userId: user.id,
      email: user.email,
      sessionVersion: user.authVersion,
    },
    config.jwtSecret,
    {
      algorithm: 'HS256',
      issuer: config.tokenIssuer,
      audience: initial ? 'wearables-password-setup' : 'wearables-web',
      subject: user.id,
      expiresIn: expiry,
    },
  );
  res.cookie(initial ? 'password_setup' : 'jwt', token, {
    ...baseCookieOptions,
    maxAge: expiry * 1000,
  });
};
async function setupUser(req: Request): Promise<JwtPayload | undefined> {
  let claim: jwt.JwtPayload;
  try {
    const token = parseCookies(req.headers.cookie).password_setup;
    if (!token) return undefined;
    const value = jwt.verify(token, config.jwtSecret, {
      algorithms: ['HS256'],
      issuer: config.tokenIssuer,
      audience: 'wearables-password-setup',
    });
    if (
      typeof value === 'string' ||
      value.type !== 'password-setup' ||
      value.auth_method !== 'password-v1' ||
      value.userId !== value.sub ||
      typeof value.userId !== 'string' ||
      !Number.isSafeInteger(value.sessionVersion) ||
      value.sessionVersion < 1 ||
      typeof value.email !== 'string' ||
      typeof value.exp !== 'number'
    )
      return undefined;
    claim = value;
  } catch {
    return undefined;
  }
  const user = await getUserById(claim.userId);
  if (
    !user ||
    user.status !== 'approved' ||
    user.email !== claim.email ||
    user.authVersion !== claim.sessionVersion
  )
    return undefined;
  return { userId: user.id, sessionVersion: user.authVersion, email: user.email };
}
type PasswordDecision = {
  allowed: boolean;
  user: UserDto | null;
  password_change_required: boolean;
};
const checkedDecision = (value: PasswordDecision) => {
  if (
    !value ||
    typeof value.allowed !== 'boolean' ||
    typeof value.password_change_required !== 'boolean'
  )
    throw new ControlApiError(503);
  if (!value.allowed) return undefined;
  const user = fromDto(value.user!);
  if (user.status !== 'approved') throw new ControlApiError(503);
  return user;
};
const secretString = (value: unknown): value is string =>
  typeof value === 'string' && value.length >= 1 && value.length <= 256;

router.post('/register', (_req, res) =>
  res
    .status(410)
    .json({
      code: 'SELF_REGISTRATION_DISABLED',
      error: 'Contact an administrator for an account.',
    }),
);
router.get('/verify-magiclink', (_req, res) =>
  res
    .status(410)
    .json({ code: 'EMAIL_LOGIN_DISABLED', error: 'Use your individual password to sign in.' }),
);
router.post(
  '/login',
  asyncRoute(async (req, res) => {
    const { email, password, ...unknown } = req.body ?? {};
    if (
      typeof email !== 'string' ||
      email.length > 320 ||
      !secretString(password) ||
      Object.keys(unknown).length
    ) {
      res.status(400).json({ error: 'Email and password are required.' });
      return;
    }
    clearAllCookies(req, res);
    const decision = await controlRequest<PasswordDecision>('/password/login', 'POST', {
      email,
      password,
    });
    const user = checkedDecision(decision);
    if (!user) {
      res.status(401).json({ error: 'Invalid email or password.' });
      return;
    }
    issueSession(res, user, decision.password_change_required);
    res.json(
      decision.password_change_required
        ? { passwordChangeRequired: true }
        : { authenticated: true },
    );
  }),
);

for (const initial of [true, false]) {
  router.post(
    initial ? '/password/setup' : '/account/password',
    ...(initial ? [] : [auth.required]),
    asyncRoute(async (req, res) => {
      const user = initial ? await setupUser(req) : req.user;
      if (!user) {
        res.status(401).json({ error: 'Sign in again before changing your password.' });
        return;
      }
      const { currentPassword, newPassword, ...unknown } = req.body ?? {};
      if (
        !secretString(currentPassword) ||
        !secretString(newPassword) ||
        Object.keys(unknown).length
      ) {
        res.status(422).json({ error: 'Current and new passwords are required.' });
        return;
      }
      const decision = await controlRequest<PasswordDecision>(
        initial ? '/password/setup' : '/password/change',
        'POST',
        {
          actor_id: user.userId,
          actor_auth_version: user.sessionVersion,
          current_password: currentPassword,
          new_password: newPassword,
        },
      );
      const changed = checkedDecision(decision);
      if (!changed) {
        res.status(400).json({ error: 'The current password was not accepted.' });
        return;
      }
      if (
        changed.id !== user.userId ||
        changed.authVersion !== user.sessionVersion + 1 ||
        decision.password_change_required
      )
        throw new ControlApiError(503);
      clearAllCookies(req, res);
      issueSession(res, changed);
      res.json({ authenticated: true });
    }),
  );
}

router.post(
  '/admin/users',
  ...auth.adminOnly,
  asyncRoute(async (req, res) => {
    const { email, name, isAdmin, roles, temporaryPassword, ...unknown } = req.body ?? {};
    if (!secretString(temporaryPassword) || Object.keys(unknown).length) {
      res.status(422).json({ error: 'Invalid staff account details.' });
      return;
    }
    const user = fromDto(
      await controlRequest<UserDto>('/users', 'POST', {
        email,
        name,
        is_admin: isAdmin,
        roles,
        temporary_password: temporaryPassword,
        actor_id: req.user!.userId,
        actor_auth_version: req.user!.sessionVersion,
      }),
    );
    res.status(201).json({ user: serializeUser(user), passwordChangeRequired: true });
  }),
);
router.post(
  '/admin/users/:userId/password-reset',
  ...auth.adminOnly,
  asyncRoute(async (req, res) => {
    const { temporaryPassword, expectedRevision, ...unknown } = req.body ?? {};
    if (!secretString(temporaryPassword) || Object.keys(unknown).length) {
      res.status(422).json({ error: 'A new temporary password is required.' });
      return;
    }
    const user = fromDto(
      await controlRequest<UserDto>(
        `/users/${encodeURIComponent(req.params.userId)}/password-reset`,
        'POST',
        {
          temporary_password: temporaryPassword,
          expected_revision: expectedRevision,
          actor_id: req.user!.userId,
          actor_auth_version: req.user!.sessionVersion,
        },
      ),
    );
    res.json({ user: serializeUser(user), passwordChangeRequired: true });
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
        roleRequestStatuses: req.user.roleRequestStatuses ?? defaultRoleRequestStatuses(),
      },
    });
  }),
);
// Account roles are assigned directly by an administrator, not self-requested.
router.post(['/request-admin', '/request-role'], auth.required, (_req, res) => {
  res.status(410).json({ error: 'ADMIN_MANAGED_ACCESS' });
});
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
  const pendingRequests = (await listAccessRequests('pending')).map((request) => ({
    ...serializeUser(request.user),
    requestType: request.requestType,
    requestedAt: request.requestedAt ? request.requestedAt.toISOString() : undefined,
  }));
  res.json({ users: pendingRequests });
};
router.get(
  '/admin/pending-access-requests',
  ...auth.adminOnly,
  asyncRoute(sendPendingAccessRequests),
);
const updateUserStatus = async (req: Request, res: Response, status: UserStatus) => {
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
  if (status !== 'approved' && isActiveAdmin && (await countActiveAdmins()) <= 1) {
    res.status(409).json({
      error: 'At least one admin required',
      message: 'You must keep at least one active admin account.',
      code: 'LAST_ADMIN',
    });
    return;
  }
  const updated = await setUserStatus(userId, status, req.user!);
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
    const updated = await reviewAccessRequest(userId, 'admin', 'approved', req.user!);
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
    const updated = await reviewAccessRequest(userId, 'admin', 'denied', req.user!);
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
const reviewRoleRequest = async (req: Request, res: Response, decision: 'approved' | 'denied') => {
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
  const updated = await reviewAccessRequest(userId, role, decision, req.user!);
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
    const updated = await reviewAccessRequest(userId, requestType, decision, req.user!);
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
    const normalizedRoleList = roleListFromBody ? Array.from(new Set(roleListFromBody)) : undefined;
    const hasInvalidRole = normalizedRoleList?.some((entry) => !isNonAdminRole(entry)) ?? false;
    if (hasInvalidRole) {
      res.status(400).json({ error: 'Invalid roles' });
      return;
    }
    const typedRoles = normalizedRoleList as NonAdminRole[] | undefined;
    if (requestedIsAdmin && typedRoles && typedRoles.length > 0) {
      res.status(400).json({ error: 'Admin users cannot have non-admin roles.' });
      return;
    }
    const isValidStatus =
      !status || status === 'approved' || status === 'pending' || status === 'denied';
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
      res.status(400).json({ error: 'Non-admin users must have at least one role.' });
      return;
    }
    const nextStatus = (status as UserRecord['status'] | undefined) ?? userRecord.status;
    const isActiveAdmin = userRecord.isAdmin && userRecord.status === 'approved';
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
    const updated = await updateUserAccess(
      userId,
      {
        isAdmin: requestedIsAdmin,
        roles: typedRoles,
        status: status as UserRecord['status'] | undefined,
      },
      req.user!,
    );
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
  '/logout',
  asyncRoute(async (req: Request, res: Response) => {
    const user = (await getUserFromRequest(req)) ?? (await setupUser(req));
    if (user) await revokeUserSessions(user.userId, user.sessionVersion);
    clearAllCookies(req, res);
    res.clearCookie('jwt', baseCookieOptions);
    res.json({ success: true });
  }),
);
export default router;
