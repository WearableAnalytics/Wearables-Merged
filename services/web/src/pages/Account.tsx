import { useMemo, useState } from 'react';
import type { NonAdminRole } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { StatusCallout } from '@/components/custom/StatusCallout';
import { Button } from '@/components/ui/button';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { useTheme, type ThemePreference } from '@/context/ThemeContext';
import {
  formatAccessLabel,
  getMissingNonAdminRole,
  getRoleRequestStatus,
  isAdminUser,
} from '@/lib/userAccess';

const THEME_OPTIONS: Array<{ value: ThemePreference; label: string }> = [
  { value: 'system', label: 'System theme' },
  { value: 'light', label: 'Light mode' },
  { value: 'dark', label: 'Dark mode' },
];

const roleLabel = (role: NonAdminRole) => (role === 'practitioner' ? 'Practitioner' : 'Researcher');

export function AccountPage() {
  const { user, refreshUser } = useAuth();
  const { preference, setThemePreference } = useTheme();
  const [isSubmittingAdmin, setIsSubmittingAdmin] = useState(false);
  const [isSubmittingRole, setIsSubmittingRole] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const adminRequestStatus = user?.adminRequestStatus ?? 'none';
  const isAdmin = isAdminUser(user);
  const missingRole = getMissingNonAdminRole(user);
  const missingRoleRequestStatus = missingRole ? getRoleRequestStatus(user, missingRole) : 'none';
  const accessLabel = useMemo(() => formatAccessLabel(user), [user]);

  const handleRequestAdmin = async () => {
    setIsSubmittingAdmin(true);
    setError(null);
    setMessage(null);
    try {
      const data = await defaultApi.requestAdminAccess();
      const responseMessage =
        (data as { message?: string }).message ?? 'Admin request submitted.';
      setMessage(responseMessage);
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to request admin access.');
    } finally {
      setIsSubmittingAdmin(false);
    }
  };

  const handleRequestRole = async (role: NonAdminRole) => {
    setIsSubmittingRole(true);
    setError(null);
    setMessage(null);
    try {
      const data = await defaultApi.requestRoleAccess(role);
      const responseMessage =
        (data as { message?: string }).message ?? `${roleLabel(role)} request submitted.`;
      setMessage(responseMessage);
      await refreshUser();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to request role access.');
    } finally {
      setIsSubmittingRole(false);
    }
  };

  if (!user) {
    return null;
  }

  const canRequestAdmin = !isAdmin && adminRequestStatus !== 'pending';
  const canRequestMissingRole = !isAdmin && !!missingRole && missingRoleRequestStatus !== 'pending';
  const adminRequestPending = adminRequestStatus === 'pending';
  const roleRequestPending = Boolean(missingRole && missingRoleRequestStatus === 'pending');
  let adminButtonLabel = 'Request admin access';
  if (adminRequestPending) {
    adminButtonLabel = 'Admin request pending';
  } else if (isSubmittingAdmin) {
    adminButtonLabel = 'Submitting…';
  }

  let roleButtonLabel = '';
  if (missingRole) {
    roleButtonLabel = `Request ${roleLabel(missingRole).toLowerCase()} access`;
    if (roleRequestPending) {
      roleButtonLabel = `${roleLabel(missingRole)} request pending`;
    } else if (isSubmittingRole) {
      roleButtonLabel = 'Submitting…';
    }
  }

  return (
    <>
      <PageHeader
        label="Account"
        title="Your account"
        description="Review your access details and request additional permissions if needed."
      />

      <section className="surface-card mt-6 p-4 md:p-5">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Email</p>
          <p className="text-lg font-semibold text-foreground">{user.email}</p>
          <p className="text-sm text-muted-foreground">Access</p>
          <p className="text-base font-semibold text-foreground">{accessLabel}</p>
        </div>
      </section>

      <section className="surface-card mt-6 p-4 md:p-5">
        <h2 className="text-section-title">Settings</h2>
        <div className="mt-4 flex flex-col gap-4">
          {error ? <StatusCallout tone="error" message={error} /> : null}
          {message ? <StatusCallout tone="success" message={message} /> : null}

          <div className="space-y-2">
            <p className="m-0 text-sm font-semibold text-foreground">Theme</p>
            <div className="inline-flex w-full flex-wrap gap-2 rounded-xl border border-border bg-muted/40 p-1">
              {THEME_OPTIONS.map((option) => {
                const isActive = preference === option.value;
                return (
                  <Button
                    key={option.value}
                    type="button"
                    onClick={() => setThemePreference(option.value)}
                    variant={isActive ? 'default' : 'ghost'}
                    size="sm"
                    className="px-3"
                    aria-pressed={isActive}
                  >
                    {option.label}
                  </Button>
                );
              })}
            </div>
          </div>

          {isAdmin ? null : (
            <div className="space-y-2 pt-1">
              <p className="m-0 text-sm font-semibold text-foreground">Access requests</p>
              <div className="flex flex-wrap items-center gap-2">
                {!missingRole ? null : (
                  <Button
                    onClick={() => {
                      void handleRequestRole(missingRole);
                    }}
                    disabled={!canRequestMissingRole || isSubmittingRole || roleRequestPending}
                  >
                    {roleButtonLabel}
                  </Button>
                )}

                <Button
                  variant="outline"
                  onClick={handleRequestAdmin}
                  disabled={!canRequestAdmin || isSubmittingAdmin || adminRequestPending}
                >
                  {adminButtonLabel}
                </Button>
              </div>

              {!adminRequestPending && !roleRequestPending ? null : (
                <div className="space-y-1">
                  {missingRole && roleRequestPending ? (
                    <p className="m-0 text-sm text-muted-foreground">{roleLabel(missingRole)} request pending review.</p>
                  ) : null}
                  {adminRequestPending ? (
                    <p className="m-0 text-sm text-muted-foreground">Admin request pending review.</p>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </>
  );
}
