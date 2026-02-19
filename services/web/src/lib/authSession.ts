export const AUTH_SESSION_EXPIRED_EVENT = 'auth-session-expired';

export const LOGOUT_REASON_QUERY_PARAM = 'reason';
export const LOGOUT_REASON_EXPIRED = 'expired';
export const LOGOUT_REASON_SUCCESS = 'success';

export type LogoutReason = typeof LOGOUT_REASON_EXPIRED | typeof LOGOUT_REASON_SUCCESS;

export const getLogoutPath = (reason: LogoutReason): string =>
  `/logout?${LOGOUT_REASON_QUERY_PARAM}=${reason}`;

export const GUEST_ROUTE_PATHS = [
  '/',
  '/access',
  '/register',
  '/login',
  '/request-sent',
  '/error-magic_link',
];

export const isGuestRoute = (pathname: string): boolean =>
  GUEST_ROUTE_PATHS.includes(pathname);

export const dispatchSessionExpiredEvent = (): void => {
  if (typeof window === 'undefined') {
    return;
  }

  window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT));
};
