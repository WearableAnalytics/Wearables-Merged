import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

interface LogoProps {
  userType?: 'Retiree' | 'Startup'; // undefined ⇒ guest / not authenticated
  alwaysGuestRoutes: string[]; // if true, always navigate to home
  navigate: ReturnType<typeof useNavigate>;
  location: ReturnType<typeof useLocation>;
}

export const Logo: React.FC<LogoProps> = ({ userType, alwaysGuestRoutes, navigate, location }) => {
  const handleClick = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
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
        src="/WiseUpLogo.png"
        alt="WiseUp Logo"
        className="h-10 w-auto text-sm px-4 py-0 rounded-full border transition-shadow transition-colors cursor-pointer font-medium border border-[rgba(255,255,255,0.3)] text-foreground bg-white/40 bg-clip-padding backdrop-filter backdrop-blur-lg shadow-[0_4px_30px_rgba(0,0,0,0.1)] hover:text-primary hover:shadow-lg transform transition-transform duration-200 hover:scale-[1.05] group'"
      />
    </div>
  );
};
