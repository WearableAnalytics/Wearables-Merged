import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { BrandLogo } from '@/components/branding/BrandLogo';
import { getDefaultAuthenticatedPath } from '@/lib/userAccess';

export const Logo: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const handleClick = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (user) {
      void navigate(getDefaultAuthenticatedPath(user));
      return;
    }

    void navigate('/');
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
