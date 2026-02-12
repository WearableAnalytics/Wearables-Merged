import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

type ThemeMode = 'light' | 'dark';
export type ThemePreference = 'system' | 'light' | 'dark';

interface ThemeContextType {
  theme: ThemeMode;
  isDark: boolean;
  preference: ThemePreference;
  setThemePreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
const THEME_PREFERENCE_STORAGE_KEY = 'wearables-theme-preference';

function getSystemTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getInitialPreference(): ThemePreference {
  if (typeof window === 'undefined') return 'system';

  const storedPreference = window.localStorage.getItem(THEME_PREFERENCE_STORAGE_KEY);
  if (storedPreference === 'light' || storedPreference === 'dark' || storedPreference === 'system') {
    return storedPreference;
  }

  return 'system';
}

interface ThemeProviderProps {
  children: ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [preference, setPreference] = useState<ThemePreference>(getInitialPreference);
  const [systemTheme, setSystemTheme] = useState<ThemeMode>(getSystemTheme);

  const theme: ThemeMode = preference === 'system' ? systemTheme : preference;

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const updateThemeFromSystem = () => {
      setSystemTheme(mediaQuery.matches ? 'dark' : 'light');
    };

    updateThemeFromSystem();
    mediaQuery.addEventListener('change', updateThemeFromSystem);
    return () => mediaQuery.removeEventListener('change', updateThemeFromSystem);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(THEME_PREFERENCE_STORAGE_KEY, preference);
  }, [preference]);

  useEffect(() => {
    const root = document.documentElement;
    const darkMode = theme === 'dark';
    root.classList.toggle('dark', darkMode);
    root.style.colorScheme = darkMode ? 'dark' : 'light';
  }, [theme]);

  const value = useMemo(
    () => ({
      theme,
      isDark: theme === 'dark',
      preference,
      setThemePreference: setPreference,
    }),
    [preference, theme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
