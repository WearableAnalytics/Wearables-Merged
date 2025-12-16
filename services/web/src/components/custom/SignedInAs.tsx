import React from 'react';
import { useAuth } from '@/context/AuthContext';

export const SignedInAs: React.FC = () => {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <p className="mb-3 text-sm text-slate-600">
      Signed in as <span className="font-semibold text-slate-800">{user.email}</span>
      {user.name ? ` (${user.name})` : ''}
    </p>
  );
};
