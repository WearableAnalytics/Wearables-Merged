import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Menu, Shield, User } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useActiveCase } from '@/lib/activeCase';
import { useMessageToast } from '@/lib/toast';
import { useAuth } from '@/context/AuthContext';
import { LOGOUT_REASON_SUCCESS, getLogoutPath } from '@/lib/authSession';
import {
  canAccessPractitionerPages,
  canAccessResearcherPages,
  isAdminUser,
} from '@/lib/userAccess';

import { NavButton, NavButtonMobile } from './navButtons';

import { Logo } from './logo';

interface NavbarProps {
  navigate: ReturnType<typeof useNavigate>;
  location: ReturnType<typeof useLocation>;
}

export const Navbar: React.FC<NavbarProps> = ({ navigate, location }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const { activeCase, patient } = useActiveCase();
  const { user, logout } = useAuth();
  const [logoutError, setLogoutError] = useState<string | null>(null);
  useMessageToast('error', 'logout-error', logoutError);
  const isCasePage = location.pathname.startsWith('/cases/');
  const activePatientName = patient
    ? `${patient.firstName} ${patient.lastName}`
    : null;
  const isAuthenticated = !!user;
  const isAdmin = isAdminUser(user);
  const hasPractitionerAccess = canAccessPractitionerPages(user);
  const hasResearcherAccess = canAccessResearcherPages(user);

  // Add/remove body class when mobile menu changes
  useEffect(() => {
    if (isMobileMenuOpen) {
      document.body.classList.add('mobile-menu-open');
    } else {
      document.body.classList.remove('mobile-menu-open');
    }
  }, [isMobileMenuOpen]);

  const handleMobileLinkClick = () => {
    setIsMobileMenuOpen(false);
  };

  const handleLogout = async () => {
    try {
      setIsLoggingOut(true);
      setLogoutError(null);
      await logout();
      void navigate(getLogoutPath(LOGOUT_REASON_SUCCESS), { replace: true });
    } catch {
      setLogoutError('Logout could not be confirmed. Please try again.');
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <nav className="w-full fixed top-0 left-0 right-0 z-50 border-b border-border bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between gap-4 h-16">
          <Logo />

          {/* Desktop Navigation */}
          {isAuthenticated && (hasPractitionerAccess || hasResearcherAccess) ? (
            <div className="hidden md:flex min-w-0 items-center gap-3 lg:gap-6">
              {hasPractitionerAccess ? (
                <NavButton path="/overview">Overview</NavButton>
              ) : null}
              {hasPractitionerAccess &&
              isCasePage &&
              activeCase &&
              activePatientName ? (
                <NavButton
                  path={`/cases/${activeCase.caseId}`}
                  className="min-w-[7rem]"
                  title={activePatientName}
                >
                  <span className="block max-w-[12rem] truncate lg:max-w-[20rem]">
                    {activePatientName}
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
          <div className="hidden md:flex shrink-0 items-center space-x-3">
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
                    <span className="sr-only">Staff accounts</span>
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
                <NavButton
                  invertedColors={true}
                  onClick={handleLogout}
                  isDisabled={isLoggingOut}
                >
                  Logout
                </NavButton>
              </>
            ) : (
              <>
                <NavButton path="/login" invertedColors={true}>
                  Login
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
                      </span>
                    </NavButtonMobile>
                  ) : null}
                  {hasPractitionerAccess &&
                  isCasePage &&
                  activeCase &&
                  activePatientName ? (
                    <NavButtonMobile
                      path={`/cases/${activeCase.caseId}`}
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
                      <span
                        className="block max-w-full truncate"
                        title={activePatientName ?? undefined}
                      >
                        {activePatientName}
                      </span>
                    </NavButtonMobile>
                  ) : null}
                  {hasPractitionerAccess ? (
                    <NavButtonMobile
                      path="/add-case"
                      className="w-full justify-start text-left"
                      onClick={handleMobileLinkClick}
                    >
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
