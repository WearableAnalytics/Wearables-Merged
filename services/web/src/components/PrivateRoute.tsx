import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { StatusCallout, type StatusTone } from '@/components/custom/StatusCallout';
import { useAuth } from '@/context/AuthContext';
import { canAccessPractitionerPages, canAccessResearcherPages, isAdminUser } from '@/lib/userAccess';

type PrivateRouteProps = {
  children: React.ReactElement;
  requireAdmin?: boolean;
  requirePractitionerOrAdmin?: boolean;
  requireResearcherOrAdmin?: boolean;
};

export const PrivateRoute: React.FC<PrivateRouteProps> = ({
  children,
  requireAdmin = false,
  requirePractitionerOrAdmin = false,
  requireResearcherOrAdmin = false,
}) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-muted-foreground">
        Checking authentication…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (user.status && user.status !== 'approved') {
    let tone: StatusTone = 'warning';
    const message =
      user.status === 'pending'
        ? 'Your account is awaiting admin approval.'
        : 'Unable to access the application. Please contact support.';
    if (user.status !== 'pending') {
      tone = 'error';
    }
    return (
      <div className="flex min-h-[50vh] w-full items-center justify-center px-4">
        <StatusCallout tone={tone} message={message} className="w-full max-w-2xl" />
      </div>
    );
  }

  if (requireAdmin && !isAdminUser(user)) {
    return <Navigate to="/account" replace />;
  }

  if (requirePractitionerOrAdmin && !canAccessPractitionerPages(user)) {
    return <Navigate to="/account" replace />;
  }

  if (requireResearcherOrAdmin && !canAccessResearcherPages(user)) {
    return <Navigate to="/account" replace />;
  }

  return children;
};
