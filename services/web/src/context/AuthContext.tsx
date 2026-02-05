import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import { defaultApi } from '@/api/defaultApi';

export interface User {
  id: string;
  email: string;
  name?: string;
  role?: 'admin' | 'user';
  status?: 'pending' | 'approved' | 'denied';
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (): Promise<void> => {
    try {
      const currentUser = await defaultApi.me();
      setUser(currentUser as User | null);
    } catch (error) {
      console.error('Auth error:', error);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await defaultApi.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setUser(null);
      window.dispatchEvent(new Event('auth-change'));
    }
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    setLoading(true);
    await fetchUser();
  }, [fetchUser]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void fetchUser();
    }, 200);

    return () => clearTimeout(timer);
  }, [fetchUser]);

  useEffect(() => {
    const handleAuthChange = () => void refreshUser();
    window.addEventListener('auth-change', handleAuthChange);
    return () => window.removeEventListener('auth-change', handleAuthChange);
  }, [refreshUser]);

  const value: AuthContextType = {
    user,
    loading,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
