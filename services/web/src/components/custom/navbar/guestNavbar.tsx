import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Menu } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

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

  return (
    <nav className="w-full fixed top-0 left-0 right-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Logo alwaysGuestRoutes={alwaysGuestRoutes} navigate={navigate} location={location} />

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center space-x-6">
            <NavButton path="/">About</NavButton>
            <NavButton path="/for-startups">For Startups</NavButton>
            <NavButton path="/for-retirees">For Retirees</NavButton>
            <NavButton path="/signup">Sign Up</NavButton>
          </div>

          {/* Desktop Login Button */}
          <div className="hidden md:block">
            <NavButton path="/login" invertedColors={true}>
              Login
            </NavButton>
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
              <NavButtonMobile
                path="/"
                className="w-full justify-start text-left"
                onClick={handleMobileLinkClick}
              >
                About
              </NavButtonMobile>
              <NavButtonMobile
                path="/for-startups"
                className="w-full justify-start text-left"
                onClick={handleMobileLinkClick}
              >
                For Startups
              </NavButtonMobile>
              <NavButtonMobile
                path="/for-retirees"
                className="w-full justify-start text-left"
                onClick={handleMobileLinkClick}
              >
                For Retirees
              </NavButtonMobile>
              <NavButtonMobile
                path="/signup"
                className="w-full justify-start text-left"
                onClick={handleMobileLinkClick}
              >
                Sign Up
              </NavButtonMobile>
              <div className="pt-2 border-t border-muted">
                <NavButtonMobile
                  invertedColors={true}
                  path="/login"
                  className="w-full justify-start text-left"
                  onClick={handleMobileLinkClick}
                >
                  Login
                </NavButtonMobile>
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
};
