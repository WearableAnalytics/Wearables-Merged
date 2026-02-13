import React from 'react';
import { useTheme } from '@/context/ThemeContext';
import { type BrandLogoType, resolveBrandLogo } from '@/lib/brandLogos';
import { cn } from '@/lib/utils';

interface BrandLogoProps extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src'> {
  logoType: BrandLogoType;
  containerClassName?: string;
}

export const BrandLogo: React.FC<BrandLogoProps> = ({
  logoType,
  alt,
  className,
  containerClassName,
  ...imgProps
}) => {
  const { theme } = useTheme();
  const resolvedLogo = resolveBrandLogo(logoType, theme);

  if (!resolvedLogo) {
    return null;
  }

  return (
    <span className={cn('inline-flex items-center justify-center', containerClassName)}>
      <img
        src={resolvedLogo.src}
        alt={alt}
        className={cn('block object-contain', className)}
        {...imgProps}
      />
    </span>
  );
};
