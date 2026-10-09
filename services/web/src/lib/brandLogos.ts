export type BrandTheme = 'light' | 'dark';
export type BrandLogoType = 'square' | 'horizontal';

interface LogoVariants {
  light?: string;
  dark?: string;
}

export interface ResolvedBrandLogo {
  src: string;
  assetTheme: BrandTheme;
  usesFallback: boolean;
}

const logoAssets: Record<BrandLogoType, LogoVariants> = {
  square: {},
  horizontal: {},
};

const discoveredLogoModules = import.meta.glob('../assets/branding/logos/*/*.{png,jpg,jpeg,svg,webp,avif,gif,ico}', {
  eager: true,
  import: 'default',
}) as Record<string, string>;

for (const [filePath, assetUrl] of Object.entries(discoveredLogoModules)) {
  const match = filePath.match(/branding\/logos\/(square|horizontal)\/(light|dark)\.[^/.]+$/);
  if (!match) {
    continue;
  }

  const [, logoType, theme] = match as [string, BrandLogoType, BrandTheme];
  logoAssets[logoType][theme] = assetUrl;
}

function oppositeTheme(theme: BrandTheme): BrandTheme {
  return theme === 'light' ? 'dark' : 'light';
}

export function resolveBrandLogo(logoType: BrandLogoType, theme: BrandTheme): ResolvedBrandLogo | null {
  const preferredAsset = logoAssets[logoType][theme];
  if (preferredAsset) {
    return {
      src: preferredAsset,
      assetTheme: theme,
      usesFallback: false,
    };
  }

  const fallbackTheme = oppositeTheme(theme);
  const fallbackAsset = logoAssets[logoType][fallbackTheme];
  if (!fallbackAsset) {
    return null;
  }

  return {
    src: fallbackAsset,
    assetTheme: fallbackTheme,
    usesFallback: true,
  };
}
