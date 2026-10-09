import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type SharedNavButtonProps = {
  path?: string;
  children: React.ReactNode;
  isDisabled?: boolean;
  className?: string;
  onClick?: () => void;
  id?: string;
  title?: string;
  invertedColors?: boolean;
};

type NavButtonProps = SharedNavButtonProps & {
  iconOnly?: boolean;
};

function useNavButtonBehavior(path: string | undefined, onClick: (() => void) | undefined) {
  const navigate = useNavigate();
  const location = useLocation();
  const isActive = !path || location.pathname === path || location.pathname.startsWith(`${path}/`);

  const handleClick = () => {
    if (path) {
      void navigate(path);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
    onClick?.();
  };

  return { isActive, handleClick };
}

export const NavButton: React.FC<NavButtonProps> = ({
  path,
  children,
  className = '',
  onClick,
  id,
  title,
  isDisabled,
  invertedColors,
  iconOnly = false,
}) => {
  const { isActive, handleClick } = useNavButtonBehavior(path, onClick);

  const desktopInactiveClass = !invertedColors
    ? 'border-primary bg-card/40 bg-clip-padding text-foreground backdrop-blur-lg shadow-[var(--shadow-card)] hover:bg-card/55 hover:text-primary hover:shadow-md'
    : 'border-primary bg-card/40 bg-clip-padding text-foreground backdrop-blur-lg shadow-[var(--shadow-card)] hover:bg-card/55 hover:shadow-md';

  return (
    <Button
      type="button"
      id={id}
      title={title}
      onClick={isDisabled ? undefined : handleClick}
      disabled={isDisabled}
      size={iconOnly ? 'icon' : 'default'}
      variant={isActive ? 'default' : 'outline'}
      className={cn(
        'border border-transparent rounded-full font-medium transition-transform duration-200 ease-out',
        !isDisabled && !iconOnly ? 'hover:scale-[1.03]' : '',
        !iconOnly ? 'px-3 text-sm lg:px-5' : 'p-0',
        isActive ? 'border-primary shadow-md hover:shadow-md' : desktopInactiveClass,
        className,
      )}
    >
      {children}
    </Button>
  );
};

export const NavButtonMobile: React.FC<SharedNavButtonProps> = ({
  path,
  children,
  className = '',
  onClick,
  id,
  isDisabled,
  invertedColors,
}) => {
  const { isActive, handleClick } = useNavButtonBehavior(path, onClick);

  const mobileInactiveClass = !invertedColors
    ? 'border-primary bg-card/40 text-foreground hover:bg-card/55 hover:text-primary hover:shadow-md'
    : 'border-primary text-primary bg-card/40 hover:bg-card/55 hover:shadow-md';

  return (
    <Button
      type="button"
      onClick={isDisabled ? undefined : handleClick}
      disabled={isDisabled}
      id={id}
      size="default"
      variant={isActive ? 'default' : 'ghost'}
      className={cn(
        'w-full justify-start rounded-full px-4 text-left text-sm font-medium',
        isActive ? 'border border-primary shadow-md' : mobileInactiveClass,
        className,
      )}
    >
      {children}
    </Button>
  );
};
