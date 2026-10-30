import React, {
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
} from 'react';
import type { ReactNode } from 'react';
import { defaultApi } from '@/api/defaultApi';
import {
  AUTH_SESSION_EXPIRED_EVENT,
  dispatchUserChangedEvent,
} from '@/lib/authSession';

import { AuthContext, type User, type AuthContextType } from './authState';
export type { User } from './authState';

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const userRef = useRef<User | null>(null);
  const requestEpoch = useRef(0);

  useEffect(() => {
    userRef.current = user;
  }, [user]);

  const fetchUser = useCallback(
    async (options?: { silent?: boolean }): Promise<User | null> => {
      const epoch = ++requestEpoch.current;
      if (!options?.silent) {
        setLoading(true);
      }

      try {
        const currentUser = await defaultApi.me();
        const normalizedUser = currentUser as User | null;
        if (epoch !== requestEpoch.current) return userRef.current;
        if (userRef.current?.id !== normalizedUser?.id)
          dispatchUserChangedEvent();
        userRef.current = normalizedUser;
        setUser(normalizedUser);
        return normalizedUser;
      } catch (error) {
        if (epoch !== requestEpoch.current) return userRef.current;
        const status = (error as { status?: number }).status;
        if (status === 401 || status === 403) {
          userRef.current = null;
          setUser(null);
          return null;
        }
        return userRef.current;
      } finally {
        if (epoch === requestEpoch.current && !options?.silent) {
          setLoading(false);
        }
      }
    },
    [],
  );

  const logout = useCallback(async (): Promise<void> => {
    ++requestEpoch.current;
    try {
      await defaultApi.logout();
      userRef.current = null;
      setUser(null);
      dispatchUserChangedEvent();
    } finally {
      setLoading(false);
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
      ++requestEpoch.current;
      userRef.current = null;
      setUser(null);
      setLoading(false);
    };

    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () =>
      window.removeEventListener(
        AUTH_SESSION_EXPIRED_EVENT,
        handleSessionExpired,
      );
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
