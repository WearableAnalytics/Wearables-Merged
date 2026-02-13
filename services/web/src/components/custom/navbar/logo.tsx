import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import wearablesLogo from '@/assets/Wearables.png';

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
      <img
        src={wearablesLogo}
        alt="Wearables Logo"
        className="h-10 w-auto text-sm px-4 py-0 rounded-full border border-border/70 transition-shadow transition-colors cursor-pointer font-medium text-foreground bg-card/40 bg-clip-padding backdrop-filter backdrop-blur-lg shadow-[var(--shadow-card)] hover:text-primary hover:shadow-lg transform transition-transform duration-200 hover:scale-[1.05] group"
      />
    </div>
  );
};
