import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Menu } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useActiveCase } from '@/lib/activeCase';
import { useAuth } from '@/context/AuthContext';

import { NavButton, NavButtonMobile } from './navButtons';

import { Logo } from './logo';

interface GuestNavbarProps {
  alwaysGuestRoutes: string[];
  navigate: ReturnType<typeof useNavigate>;
  location: ReturnType<typeof useLocation>;
}

export const GuestNavbar: React.FC<GuestNavbarProps> = ({
  alwaysGuestRoutes,
  navigate,
  location,
}) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const { activeCase, patient } = useActiveCase();
  const { user, logout } = useAuth();
  const isCasePage = location.pathname.startsWith('/cases/');
  const activePatientName = patient ? `${patient.firstName} ${patient.lastName}` : null;
  const isAuthenticated = !!user;

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
      void navigate('/login');
    }
  };

  return (
    <nav className="w-full fixed top-0 left-0 right-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Logo alwaysGuestRoutes={alwaysGuestRoutes} navigate={navigate} location={location} />

          {/* Desktop Navigation */}
          {isAuthenticated ? (
            <div className="hidden md:flex items-center space-x-6">
              <NavButton path="/overview">Overview</NavButton>
              {isCasePage && activeCase && activePatientNavLabel ? (
                <NavButton path={`/cases/${activeCase.caseId}`}>
                  <span className="max-w-[180px] truncate" title={activePatientName ?? undefined}>
                    {activePatientNavLabel}
                  </span>
                </NavButton>
              ) : null}
              <NavButton path="/add-case">Add Case</NavButton>
            </div>
          ) : (
            <div className="hidden md:flex items-center space-x-6" />
          )}

          {/* Desktop Auth Buttons */}
          <div className="hidden md:flex items-center space-x-3">
            {isAuthenticated ? (
              <NavButton invertedColors={true} onClick={handleLogout} isDisabled={isLoggingOut}>
                Logout
              </NavButton>
            ) : (
              <>
                <NavButton path="/login" invertedColors={true}>
                  Login
                </NavButton>
                <NavButton path="/register">Register</NavButton>
              </>
            )}
          </div>

          {/* Mobile menu button */}
          <div className="md:hidden">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="p-2 hover:bg-primary group"
            >
              <Menu className="h-6 w-6 text-foreground group-hover:text-primary-foreground" />
            </Button>
          </div>
        </div>

        {/* Mobile menu */}
        {isMobileMenuOpen && (
          <div className="md:hidden absolute top-16 left-0 right-0 bg-background border-b border-border shadow-lg z-50">
            <div className="px-4 py-3 space-y-2">
              {isAuthenticated ? (
                <>
                  <NavButtonMobile
                    path="/overview"
                    className="w-full justify-start text-left"
                    onClick={handleMobileLinkClick}
                  >
                    Overview
                  </NavButtonMobile>
                  {isCasePage && activeCase && activePatientMobileLabel ? (
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
                  <NavButtonMobile path="/add-case" className="w-full justify-start text-left" onClick={handleMobileLinkClick}>
                    Add Case
                  </NavButtonMobile>
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
