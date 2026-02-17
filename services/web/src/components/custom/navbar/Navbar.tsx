import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Menu, Shield, User } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useActiveCase } from '@/lib/activeCase';
import { defaultApi } from '@/api/defaultApi';
import {
  ADMIN_APPROVALS_UPDATED_EVENT,
  type AdminApprovalsUpdatedDetail,
} from '@/lib/adminApprovalsEvents';
import { useAuth } from '@/context/AuthContext';
import { LOGOUT_REASON_SUCCESS, getLogoutPath } from '@/lib/authSession';
import { canAccessPractitionerPages, canAccessResearcherPages, isAdminUser } from '@/lib/userAccess';

import { NavButton, NavButtonMobile } from './navButtons';

import { Logo } from './logo';

interface NavbarProps {
  navigate: ReturnType<typeof useNavigate>;
  location: ReturnType<typeof useLocation>;
}

export const Navbar: React.FC<NavbarProps> = ({
  navigate,
  location,
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [openApprovalsCount, setOpenApprovalsCount] = useState(0);
  const { activeCase, patient } = useActiveCase();
  const { user, logout } = useAuth();
  const isCasePage = location.pathname.startsWith('/cases/');
  const activePatientName = patient ? `${patient.firstName} ${patient.lastName}` : null;
  const isAuthenticated = !!user;
  const isAdmin = isAdminUser(user);
  const hasPractitionerAccess = canAccessPractitionerPages(user);
  const hasResearcherAccess = canAccessResearcherPages(user);

  const activePatientNavLabel =
    patient && patient.lastName
      ? `${patient.firstName.charAt(0)} ${patient.lastName.length > 7 ? `${patient.lastName.slice(0, 5)}…` : patient.lastName.slice(0, 7)}`
      : null;

  const activePatientMobileLabel = activePatientName ?? activePatientNavLabel;

  // Add/remove body class when mobile menu changes
  useEffect(() => {
    if (isMobileMenuOpen) {
      document.body.classList.add('mobile-menu-open');
    } else {
      document.body.classList.remove('mobile-menu-open');
    }
  }, [isMobileMenuOpen]);

  useEffect(() => {
    if (!isAuthenticated || !isAdmin) {
      setOpenApprovalsCount(0);
      return;
    }

    let cancelled = false;

    const loadOpenApprovalsCount = async () => {
      try {
        const [pendingUsersData, pendingAccessRequestsData] = await Promise.all([
          defaultApi.listPendingUsers(),
          defaultApi.listPendingAccessRequests(),
        ]);
        if (cancelled) {
          return;
        }

        const pendingUsers = (pendingUsersData as { users?: unknown[] }).users ?? [];
        const pendingAccessRequests = (pendingAccessRequestsData as { users?: unknown[] }).users ?? [];
        setOpenApprovalsCount(pendingUsers.length + pendingAccessRequests.length);
      } catch (error) {
        if (!cancelled) {
          console.error('Failed to load open approvals count:', error);
          setOpenApprovalsCount(0);
        }
      }
    };

    void loadOpenApprovalsCount();
    const refreshId = window.setInterval(() => {
      void loadOpenApprovalsCount();
    }, 30_000);

    const handleApprovalsUpdated = (event: Event) => {
      const customEvent = event as CustomEvent<AdminApprovalsUpdatedDetail>;
      const nextCount = customEvent.detail?.openRequestsCount;
      if (typeof nextCount === 'number') {
        setOpenApprovalsCount(nextCount);
        return;
      }
      void loadOpenApprovalsCount();
    };
    const handleWindowFocus = () => {
      void loadOpenApprovalsCount();
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void loadOpenApprovalsCount();
      }
    };

    window.addEventListener(ADMIN_APPROVALS_UPDATED_EVENT, handleApprovalsUpdated);
    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      cancelled = true;
      window.clearInterval(refreshId);
      window.removeEventListener(ADMIN_APPROVALS_UPDATED_EVENT, handleApprovalsUpdated);
      window.removeEventListener('focus', handleWindowFocus);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [isAdmin, isAuthenticated, location.pathname]);

  const handleMobileLinkClick = () => {
    setIsMobileMenuOpen(false);
  };

  const handleLogout = async () => {
    try {
      setIsLoggingOut(true);
      await logout();
    } catch (err) {
      console.error('Logout failed:', err);
    } finally {
      setIsLoggingOut(false);
      void navigate(getLogoutPath(LOGOUT_REASON_SUCCESS), { replace: true });
    }
  };

  return (
    <nav className="w-full fixed top-0 left-0 right-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div
          className={`flex items-center justify-between h-16 ${
            isMobileMenuOpen ? 'bg-background border-b border-border' : ''
          }`}
        >
          <Logo />

          {/* Desktop Navigation */}
          {isAuthenticated && (hasPractitionerAccess || hasResearcherAccess) ? (
            <div className="hidden md:flex items-center space-x-6">
              {hasPractitionerAccess ? (
                <NavButton path="/overview">Overview</NavButton>
              ) : null}
              {hasPractitionerAccess && isCasePage && activeCase && activePatientNavLabel ? (
                <NavButton path={`/cases/${activeCase.caseId}`}>
                  <span className="max-w-[180px] truncate" title={activePatientName ?? undefined}>
                    {activePatientNavLabel}
                  </span>
                </NavButton>
              ) : null}
              {hasPractitionerAccess ? (
                <NavButton path="/add-case">Add Case</NavButton>
              ) : null}
              {hasResearcherAccess ? (
                <NavButton path="/researcher/api-access">API Access</NavButton>
              ) : null}
            </div>
          ) : (
            <div className="hidden md:flex items-center space-x-6" />
          )}

          {/* Desktop Auth Buttons */}
          <div className="hidden md:flex items-center space-x-3">
            {isAuthenticated ? (
              <>
                {isAdmin ? (
                  <NavButton
                    path="/admin/approvals"
                    invertedColors={true}
                    iconOnly
                    className="ui-control-square relative p-0 flex items-center justify-center"
                  >
                    <Shield className="h-5 w-5" aria-hidden />
                    {openApprovalsCount > 0 ? (
                      <span className="pointer-events-none absolute -right-1 -top-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-background bg-primary px-1 text-[10px] font-semibold leading-none text-primary-foreground tabular-nums">
                        {openApprovalsCount > 99 ? '99+' : openApprovalsCount}
                      </span>
                    ) : null}
                    <span className="sr-only">
                      Admin approvals{openApprovalsCount > 0 ? `, ${openApprovalsCount} open requests` : ''}
                    </span>
                  </NavButton>
                ) : null}
                <NavButton
                  path="/account"
                  invertedColors={true}
                  iconOnly
                  className="ui-control-square p-0 flex items-center justify-center"
                >
                  <User className="h-5 w-5" aria-hidden />
                  <span className="sr-only">Account</span>
                </NavButton>
                <NavButton invertedColors={true} onClick={handleLogout} isDisabled={isLoggingOut}>
                  Logout
                </NavButton>
              </>
            ) : (
              <>
                <NavButton path="/login" invertedColors={true}>
                  Login
                </NavButton>
                <NavButton path="/register" invertedColors={true}>
                  Register
                </NavButton>
              </>
            )}
          </div>

          {/* Mobile menu button */}
          <div className="md:hidden">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="group rounded-full border-border/70 bg-card/40 bg-clip-padding shadow-[var(--shadow-card)] backdrop-blur-lg hover:bg-primary"
            >
              <Menu className="h-5 w-5 text-foreground group-hover:text-primary-foreground" />
            </Button>
          </div>
        </div>

        {/* Mobile menu */}
        {isMobileMenuOpen && (
          <div className="md:hidden absolute top-16 left-0 right-0 bg-background border-b border-border shadow-lg z-50">
            <div className="px-4 py-3 space-y-2">
              {isAuthenticated ? (
                <>
                  {hasPractitionerAccess ? (
                    <NavButtonMobile
                      path="/overview"
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
                      Overview
                    </NavButtonMobile>
                  ) : null}
                  <NavButtonMobile
                    path="/account"
                    className="w-full justify-start text-left"
                    onClick={handleMobileLinkClick}
                  >
                    Account
                  </NavButtonMobile>
                  {hasResearcherAccess ? (
                    <NavButtonMobile
                      path="/researcher/api-access"
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
                      API Access
                    </NavButtonMobile>
                  ) : null}
                  {isAdmin ? (
                    <NavButtonMobile
                      path="/admin/approvals"
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
                      <span className="inline-flex items-center gap-2">
                        <span>Admin</span>
                        {openApprovalsCount > 0 ? (
                          <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-background bg-primary px-1 text-[10px] font-semibold leading-none text-primary-foreground tabular-nums">
                            {openApprovalsCount > 99 ? '99+' : openApprovalsCount}
                          </span>
                        ) : null}
                      </span>
                    </NavButtonMobile>
                  ) : null}
                  {hasPractitionerAccess && isCasePage && activeCase && activePatientMobileLabel ? (
                    <NavButtonMobile
                      path={`/cases/${activeCase.caseId}`}
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
                      <span className="block max-w-full truncate" title={activePatientName ?? undefined}>
                        {activePatientName}
                      </span>
                    </NavButtonMobile>
                  ) : null}
                  {hasPractitionerAccess ? (
                    <NavButtonMobile path="/add-case" className="w-full justify-start text-left" onClick={handleMobileLinkClick}>
                      Add Case
                    </NavButtonMobile>
                  ) : null}
                </>
              ) : null}
              <div className="pt-2 border-t border-muted">
                {isAuthenticated ? (
                  <NavButtonMobile
                    invertedColors={true}
                    className="w-full justify-start text-left"
                    onClick={() => {
                      handleMobileLinkClick();
                      void handleLogout();
                    }}
                    isDisabled={isLoggingOut}
                  >
                    Logout
                  </NavButtonMobile>
                ) : (
                  <div className="flex flex-col gap-2">
                    <NavButtonMobile
                      invertedColors={true}
                      path="/login"
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
                      Login
                    </NavButtonMobile>
                    <NavButtonMobile
                      invertedColors={true}
                      path="/register"
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
                      Register
                    </NavButtonMobile>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
};
