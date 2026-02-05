import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';

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

  if (user.status && user.status !== 'approved') {
    const message =
      user.status === 'pending'
        ? 'Your account is awaiting admin approval.'
        : 'Unable to access the application. Please contact support.';
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-red-600">
        {message}
      </div>
    );
  }

  return children;
};
