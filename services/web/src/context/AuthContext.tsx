import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';
import { defaultApi } from '@/api/defaultApi';
import { AUTH_SESSION_EXPIRED_EVENT } from '@/lib/authSession';

export interface User {
  id: string;
  email: string;
  name?: string;
  role?: 'admin' | 'user';
  status?: 'pending' | 'approved' | 'denied';
  adminRequestStatus?: 'none' | 'pending' | 'approved' | 'denied';
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  checkSessionLazily: () => Promise<User | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const userRef = useRef<User | null>(null);

  useEffect(() => {
    userRef.current = user;
  }, [user]);

  const fetchUser = useCallback(async (options?: { silent?: boolean }): Promise<User | null> => {
    if (!options?.silent) {
      setLoading(true);
    }

    try {
      const currentUser = await defaultApi.me();
      const normalizedUser = currentUser as User | null;
      setUser(normalizedUser);
      return normalizedUser;
    } catch (error) {
      console.error('Auth error:', error);
      const status = (error as { status?: number }).status;
      if (status === 401) {
        setUser(null);
        return null;
      }
      return userRef.current;
    } finally {
      if (!options?.silent) {
        setLoading(false);
      }
    }
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    try {
      await defaultApi.logout();
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      setUser(null);
    }
  }, []);

  const refreshUser = useCallback(async (): Promise<void> => {
    await fetchUser();
  }, [fetchUser]);

  const checkSessionLazily = useCallback(async (): Promise<User | null> => {
    return fetchUser({ silent: true });
  }, [fetchUser]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void fetchUser();
    }, 200);

    return () => clearTimeout(timer);
  }, [fetchUser]);

  useEffect(() => {
    const handleSessionExpired = () => {
      setUser(null);
      setLoading(false);
    };

    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const value: AuthContextType = {
    user,
    loading,
    logout,
    refreshUser,
    checkSessionLazily,
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
