import { createContext } from 'react';

export interface User {
  id: string;
  email: string;
  name?: string;
  isAdmin?: boolean;
  roles?: Array<'practitioner' | 'researcher'>;
  status?: 'pending' | 'approved' | 'denied';
  adminRequestStatus?: 'none' | 'pending' | 'approved' | 'denied';
  roleRequestStatuses?: Partial<
    Record<
      'practitioner' | 'researcher',
      'none' | 'pending' | 'approved' | 'denied'
    >
  >;
}

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  checkSessionLazily: () => Promise<User | null>;
}

export const AuthContext = createContext<AuthContextType | undefined>(
  undefined,
);
