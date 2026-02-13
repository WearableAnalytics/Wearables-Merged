import { useEffect, useState } from 'react';
import { PageHeader } from '@/components/custom/PageHeader';
import { AddCaseNotice } from '@/pages/add-case/components/AddCaseNotice';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { useTheme, type ThemePreference } from '@/context/ThemeContext';

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

  useEffect(() => {
    if (error) {
      toast.error(error, { id: 'account-error' });
    } else {
      toast.dismiss('account-error');
    }
  }, [error]);

  useEffect(() => {
    if (message) {
      toast.info(message, { id: 'account-message' });
    } else {
      toast.dismiss('account-message');
    }
  }, [message]);

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

  useEffect(() => {
    if (!user) {
      toast.dismiss('account-pending');
      return;
    }

    if (adminRequestStatus === 'pending') {
      toast.info('Your admin request is pending review.', { id: 'account-pending' });
    } else {
      toast.dismiss('account-pending');
    }
  }, [adminRequestStatus, user]);

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

      <section className="mt-6 bg-white border border-slate-200 shadow-[0_12px_30px_rgba(15,23,42,0.06)] rounded-2xl p-4 md:p-5">
        <div className="space-y-2">
          <p className="text-sm text-slate-500">Email</p>
          <p className="text-lg font-semibold text-slate-900">{user.email}</p>
          <p className="text-sm text-slate-500">Role</p>
          <p className="text-base font-semibold capitalize text-slate-900">{user.role ?? 'user'}</p>
          <p className="text-sm text-slate-500">Account status</p>
          <p className="text-base font-semibold capitalize text-slate-900">{user.status ?? 'approved'}</p>
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

      <section className="mt-6 bg-white border border-slate-200 shadow-[0_12px_30px_rgba(15,23,42,0.06)] rounded-2xl p-4 md:p-5">
        <h2 className="m-0 text-lg font-semibold text-slate-900">Settings</h2>
        <div className="mt-4 flex flex-col gap-3">
          <p className="m-0 text-sm font-semibold text-slate-900">Theme</p>
          <div className="inline-flex w-full flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50 p-1">
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
