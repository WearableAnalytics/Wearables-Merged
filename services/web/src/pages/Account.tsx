import { useState } from 'react';
import { PageHeader } from '@/components/custom/PageHeader';
import { AddCaseNotice } from '@/pages/add-case/components/AddCaseNotice';
import { Button } from '@/components/ui/button';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';

export function AccountPage() {
  const { user, refreshUser } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  if (!user) {
    return null;
  }

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

  const adminRequestStatus = user.adminRequestStatus ?? 'none';
  const canRequestAdmin = user.role !== 'admin' && adminRequestStatus !== 'pending';

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
          {error ? <AddCaseNotice tone="error" message={error} /> : null}
          {message ? <AddCaseNotice tone="info" message={message} /> : null}

          {user.role === 'admin' ? (
            <AddCaseNotice tone="info" message="You already have admin access." />
          ) : adminRequestStatus === 'pending' ? (
            <AddCaseNotice tone="loading" message="Your admin request is pending review." />
          ) : (
            <Button onClick={handleRequestAdmin} disabled={!canRequestAdmin || isSubmitting}>
              {isSubmitting ? 'Submitting…' : 'Request admin access'}
            </Button>
          )}
        </div>
      </section>
    </>
  );
}
