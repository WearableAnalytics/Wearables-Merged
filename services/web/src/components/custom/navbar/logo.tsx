import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { BrandLogo } from '@/components/branding/BrandLogo';

interface LogoProps {
  userType?: 'Retiree' | 'Startup'; // undefined ⇒ guest / not authenticated
  alwaysGuestRoutes: string[]; // if true, always navigate to home
  navigate: ReturnType<typeof useNavigate>;
  location: ReturnType<typeof useLocation>;
}

export const Logo: React.FC<LogoProps> = ({ userType, alwaysGuestRoutes, navigate, location }) => {
  const { user } = useAuth();

  const handleClick = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (user) {
      void navigate('/overview');
      return;
    }

    if (!userType || alwaysGuestRoutes.includes(location.pathname)) {
      void navigate('/'); // guest → home
    } else if (userType === 'Retiree') {
      void navigate('/retiree/browse-jobs');
    } else {
      void navigate('/startup/browse-retirees');
    }
  };

  return (
    <div className="flex items-center cursor-pointer" onClick={handleClick}>
      <BrandLogo
        logoType="horizontal"
        alt="Wearables Logo"
        className="h-10 w-auto"
        containerClassName="rounded-full border border-border/70 bg-card/40 px-4 py-0 shadow-[var(--shadow-card)] transition-shadow transition-transform duration-200 backdrop-blur-lg hover:shadow-lg hover:scale-[1.05]"
      />
    </div>
  );
};
