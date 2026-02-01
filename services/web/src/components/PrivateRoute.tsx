import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { ALLOWED_EMAILS } from '@/config/allowedEmails';

export const PrivateRoute: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-slate-600">
        Checking authentication…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (!ALLOWED_EMAILS.includes(user.email)) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-red-600">
        Access denied: Your email is not authorized to use this application.
      </div>
    );
  }

  return children;
};
