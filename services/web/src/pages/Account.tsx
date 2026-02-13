import { useState } from 'react';
import { PageHeader } from '@/components/custom/PageHeader';
import { AddCaseNotice } from '@/pages/add-case/components/AddCaseNotice';
import { Button } from '@/components/ui/button';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { useTheme, type ThemePreference } from '@/context/ThemeContext';
import { useMessageToast } from '@/lib/toast';

const THEME_OPTIONS: Array<{ value: ThemePreference; label: string }> = [
  { value: 'system', label: 'System theme' },
  { value: 'light', label: 'Light mode' },
  { value: 'dark', label: 'Dark mode' },
];

export function AccountPage() {
  const { user, refreshUser } = useAuth();
  const { preference, setThemePreference } = useTheme();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const adminRequestStatus = user?.adminRequestStatus ?? 'none';
  const userRole = user?.role ?? 'user';
  const pendingAdminToastMessage =
    user && adminRequestStatus === 'pending' ? 'Your admin request is pending review.' : null;
  useMessageToast('error', 'account-error', error);
  useMessageToast('info', 'account-message', message);
  useMessageToast('info', 'account-pending', pendingAdminToastMessage);

  const handleRequestAdmin = async () => {
    setIsSubmitting(true);
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
      setIsSubmitting(false);
    }
  };

  if (!user) {
    return null;
  }

  const canRequestAdmin = userRole !== 'admin' && adminRequestStatus !== 'pending';

  return (
    <>
      <PageHeader
        label="Account"
        title="Your account"
        description="Review your access details and request admin privileges if needed."
      />

      <section className="surface-card mt-6 p-4 md:p-5">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">Email</p>
          <p className="text-lg font-semibold text-foreground">{user.email}</p>
          <p className="text-sm text-muted-foreground">Role</p>
          <p className="text-base font-semibold capitalize text-foreground">{user.role ?? 'user'}</p>
          <p className="text-sm text-muted-foreground">Account status</p>
          <p className="text-base font-semibold capitalize text-foreground">{user.status ?? 'approved'}</p>
        </div>

        <div className="mt-6 space-y-3">
          {userRole === 'admin' ? (
            <AddCaseNotice tone="info" message="You already have admin access." />
          ) : adminRequestStatus === 'pending' ? null : (
            <Button onClick={handleRequestAdmin} disabled={!canRequestAdmin || isSubmitting}>
              {isSubmitting ? 'Submitting…' : 'Request admin access'}
            </Button>
          )}
        </div>
      </section>

      <section className="surface-card mt-6 p-4 md:p-5">
        <h2 className="text-section-title">Settings</h2>
        <div className="mt-4 flex flex-col gap-3">
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
      </section>
    </>
  );
}
