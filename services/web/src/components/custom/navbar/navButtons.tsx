import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

export const NavButton: React.FC<{
  path?: string;
  children: React.ReactNode;
  isDisabled?: boolean;
  className?: string;
  onClick?: () => void;
  id?: string; //add id prop for tutorial
  invertedColors?: boolean;
}> = ({ path, children, className = '', onClick, id, isDisabled, invertedColors }) => {
  const navigate = useNavigate();
  const location = useLocation();

  // Mark active if the current URL starts with the button's path
  const isActive = !path || location.pathname === path || location.pathname.startsWith(path + '/');

  const handleClick = () => {
    if (path) void navigate(path);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    onClick?.();
  };

  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : handleClick}
      id={id}
      className={`text-sm px-4 py-2 rounded-full border border-1 transition-shadow transition-colors cursor-pointer ${
        isActive
          ? 'bg-primary border-primary text-primary-foreground shadow-md transform transition-transform duration-200 ease-out hover:scale-[1.05] group' // active button
          : !invertedColors
            ? 'font-medium border border-[rgba(255,255,255,0.3)] text-foreground bg-white/40 bg-clip-padding backdrop-filter backdrop-blur-lg shadow-[0_4px_30px_rgba(0,0,0,0.1)] hover:text-primary hover:border-primary hover:bg-transparent hover:shadow-lg transform transition-transform duration-200 hover:scale-[1.05] ease-out group'
            : 'font-medium text-primary border border-primary bg-transparent text-foreground bg-white/40 bg-clip-padding backdrop-filter backdrop-blur-lg shadow-[0_4px_30px_rgba(0,0,0,0.1)] hover:border-primary hover:shadow-lg transform transition-transform duration-200 hover:scale-[1.05] ease-out group'
      } ${isDisabled ? 'opacity-80' : 'cursor-pointer'} ${className}`}
    >
      {children}
    </button>
  );
};

export const NavButtonMobile: React.FC<{
  path?: string;
  children: React.ReactNode;
  isDisabled?: boolean;
  className?: string;
  onClick?: () => void;
  id?: string;
  invertedColors?: boolean;
}> = ({ path, children, className = '', onClick, id, isDisabled, invertedColors }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const isActive = !path || location.pathname === path || location.pathname.startsWith(path + '/');

  const handleClick = () => {
    if (path) void navigate(path);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    onClick?.();
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      id={id}
      className={`text-sm font-medium px-4 py-2 rounded-full border transition-shadow transition-colors cursor-pointer ${
        isActive
          ? 'bg-primary border-primary text-primary-foreground shadow-md' // is active always the same
          : !invertedColors
            ? 'border-transparent text-foreground hover:text-primary hover:border-primary hover:shadow-md' // default colors not active
            : 'border-primary text-primary bg-transparent hover:shadow-md' // inverted colors not active
      } ${isDisabled ? 'opacity-80' : 'cursor-pointer'} ${className}`}
    >
      {children}
    </button>
  );
};
