import { useCallback, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { Navbar } from './components/custom/navbar/Navbar';
import { Routing } from './Routing';
import { useAuth } from './context/AuthContext';
import { useTheme } from './context/ThemeContext';
import {
  AUTH_SESSION_EXPIRED_EVENT,
  GUEST_ROUTE_PATHS,
  LOGOUT_REASON_EXPIRED,
  getLogoutPath,
  isGuestRoute,
} from './lib/authSession';

function SessionMonitor() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, loading, checkSessionLazily } = useAuth();
  const authenticatedUserId = user?.id ?? null;

  const redirectToExpiredLogout = useCallback(() => {
    if (location.pathname === '/logout') {
      return;
    }
    void navigate(getLogoutPath(LOGOUT_REASON_EXPIRED), { replace: true });
  }, [location.pathname, navigate]);

  useEffect(() => {
    const handleSessionExpired = () => {
      if (isGuestRoute(location.pathname) || location.pathname === '/logout') {
        return;
      }
      redirectToExpiredLogout();
    };

    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, [location.pathname, redirectToExpiredLogout]);

  useEffect(() => {
    if (loading || !authenticatedUserId) {
      return;
    }
    if (isGuestRoute(location.pathname) || location.pathname === '/logout') {
      return;
    }

    let cancelled = false;

    const runLazySessionCheck = async () => {
      const currentUser = await checkSessionLazily();
      if (!cancelled && !currentUser) {
        redirectToExpiredLogout();
      }
    };

    void runLazySessionCheck();

    return () => {
      cancelled = true;
    };
  }, [
    authenticatedUserId,
    checkSessionLazily,
    loading,
    location.pathname,
    location.search,
    redirectToExpiredLogout,
  ]);

  return null;
}

function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isDark } = useTheme();
  const isCaseDetailRoute = /^\/cases\/[^/]+$/.test(location.pathname);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <SessionMonitor />
      <Navbar alwaysGuestRoutes={GUEST_ROUTE_PATHS} navigate={navigate} location={location} />
      <Toaster position="top-right" richColors closeButton theme={isDark ? 'dark' : 'light'} />

      <main className="pt-24 pb-[72px] px-[clamp(16px,4vw,48px)]">
        <div className={isCaseDetailRoute ? 'w-full' : 'mx-auto max-w-[1100px]'}>
          <Routing />
        </div>
      </main>
    </div>
  );
}

export default App;
