import express from 'express';
import type { CookieOptions, Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import crypto from 'crypto';
import { auth, parseCookies } from '../../middleware.js';

type UserRecord = {
  id: string;
  email: string;
  name?: string;
};

const router = express.Router();
const requestCookies = (req: Request) =>
  (req as Request & { cookies?: Record<string, string> }).cookies ?? parseCookies(req.headers.cookie);

// In-memory store for temporary EMAILAUTH tokens
const tokenStore = new Map<string, { email: string; expiresAt: Date }>();
// In-memory user store (replace with real DB later)
const users = new Map<string, UserRecord>();

const sameSite: CookieOptions['sameSite'] =
  process.env.NODE_ENV === 'production' ? 'strict' : 'lax';
const baseCookieOptions: CookieOptions = {
  httpOnly: true,
  secure: process.env.NODE_ENV === 'production',
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

const findUser = (email: string) => users.get(email.toLowerCase());
const createUser = (email: string): UserRecord => {
  const normalizedEmail = email.toLowerCase();
  const existing = findUser(normalizedEmail);
  if (existing) {
    return existing;
  }
  const id = crypto.randomUUID ? crypto.randomUUID() : crypto.randomBytes(16).toString('hex');
  const user: UserRecord = { id, email: normalizedEmail };
  users.set(normalizedEmail, user);
  return user;
};

const sendMagicLinkEmail = async (email: string, token: string) => {
  // TODO: wire up real mailer; for now log token for dev use
  // eslint-disable-next-line no-console
  console.log(`[magic-link] send to ${email}: ${token}`);
};

const isDevBypass = () => process.env.NODE_ENV !== 'production';

// POST /login
router.post('/login', async (req: Request, res: Response) => {
  const { email } = req.body;
  if (!email) {
    res.status(400).json({ error: 'Email required' });
    return;
  }
  try {
    const existingUser = findUser(email);
    clearAllCookies(req, res);
    if (!existingUser) {
      res.status(404).json({
        error: 'User not found',
        redirectToSignup: true,
        message: 'This email is not registered. Please sign up first.',
      });
      return;
    }

    if (isDevBypass()) {
      const jwtToken = createJwtToken(existingUser);
      setAuthCookie(res, jwtToken);
      res.json({
        message: 'Development mode: Direct authentication successful',
        userId: existingUser.id,
      });
      return;
    }

    const token = createMagicLinkToken(email);
    await sendMagicLinkEmail(email, token);
    res.json({ message: 'Magic link sent' });
  } catch (err) {
    console.error('Magic link error:', err);
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
    if (findUser(email)) {
      res.status(409).json({
        error: 'User already exists',
        message: 'This email is already registered. Please login instead.',
      });
      return;
    }

    clearAllCookies(req, res);

    const user = createUser(email);

    if (isDevBypass()) {
      const jwtToken = createJwtToken(user);
      setAuthCookie(res, jwtToken);
      res.status(201).json({
        message: 'Development mode: Direct authentication successful',
        id: user.id,
      });
    } else {
      const token = createMagicLinkToken(email);
      await sendMagicLinkEmail(email, token);
      res.status(201).json({ _id: user.id, message: 'Magic link sent' });
    }
  } catch (err) {
    console.error('Signup error:', err);
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
    const user = createUser(email);
    const jwtToken = createJwtToken(user);
    setAuthCookie(res, jwtToken);

    if (process.env.NODE_ENV === 'production') {
      const redirectPath =
        redirect && typeof redirect === 'string'
          ? decodeURIComponent(redirect)
          : '/';
      const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
      res.redirect(frontendUrl + redirectPath);
    } else {
      res.json({
        success: true,
        user: {
          id: user.id,
          email: user.email,
          name: user.name,
        },
      });
    }
  } catch (err) {
    // Always redirect to login page with error parameter
    const errorMessage = encodeURIComponent((err as Error).message || 'Invalid or expired token');
    const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173';
    res.redirect(`${frontendUrl}/login?error=${errorMessage}`);
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
    },
  });
});

router.post('/logout', (req: Request, res: Response) => {
  clearAllCookies(req, res);
  res.clearCookie('jwt', baseCookieOptions);
  res.json({ success: true });
});

export default router;
