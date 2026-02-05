import { useCallback, useEffect, useState } from 'react';
import { PageHeader } from '@/components/custom/PageHeader';
import { AddCaseNotice } from '@/pages/add-case/components/AddCaseNotice';
import { Button } from '@/components/ui/button';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';

type PendingUser = {
  id: string;
  email: string;
  name?: string;
  role?: string;
  status?: string;
  createdAt?: string;
};

export function AdminApprovalsPage() {
  const { user } = useAuth();
  const [pendingUsers, setPendingUsers] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionUserId, setActionUserId] = useState<string | null>(null);

  const loadPendingUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await defaultApi.listPendingUsers();
      const users = (data as { users?: PendingUser[] }).users ?? [];
      setPendingUsers(users);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load pending users.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPendingUsers();
  }, [loadPendingUsers]);

  const handleDecision = async (userId: string, decision: 'approve' | 'deny') => {
    setActionUserId(userId);
    setError(null);
    setMessage(null);
    try {
      if (decision === 'approve') {
        await defaultApi.approveUser(userId);
        setMessage('User approved. An approval email has been sent.');
      } else {
        await defaultApi.denyUser(userId);
        setMessage('User denied.');
      }
      setPendingUsers((current) => current.filter((entry) => entry.id !== userId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update user status.');
    } finally {
      setActionUserId(null);
    }
  };

  if (user?.role !== 'admin') {
    return (
      <>
        <PageHeader
          label="Admin"
          title="Approvals"
          description="Admin access is required to manage access requests."
        />
        <div className="mt-6">
          <AddCaseNotice tone="error" message="You do not have permission to view this page." />
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        label="Admin"
        title="Pending approvals"
        description="Review new registration requests and approve or deny access."
      />

      <section className="mt-6 bg-white border border-slate-200 shadow-[0_12px_30px_rgba(15,23,42,0.06)] rounded-2xl p-4 md:p-5">
        <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between mb-4">
          <div>
            <h2 className="m-0 text-[22px] font-semibold">Requests</h2>
            <p className="m-0 text-slate-500">
              {loading ? 'Loading pending users…' : `${pendingUsers.length} pending`}
            </p>
          </div>
        </div>

        {error ? (
          <AddCaseNotice tone="error" message={error} />
        ) : message ? (
          <AddCaseNotice tone="info" message={message} />
        ) : null}

        {loading ? (
          <div className="mt-4 rounded-xl border border-sky-200 bg-sky-50 px-3 py-3 font-semibold text-slate-900">
            Loading pending users…
          </div>
        ) : pendingUsers.length === 0 ? (
          <div className="mt-4 rounded-xl border border-sky-200 bg-sky-50 px-3 py-3 font-semibold text-slate-900">
            No pending requests.
          </div>
        ) : (
          <div className="mt-4 overflow-auto">
            <table className="w-full border-collapse text-[15px]">
              <thead className="bg-slate-50 text-left text-slate-600 font-bold">
                <tr className="border-b border-slate-200">
                  <th className="px-3 py-3">Email</th>
                  <th className="px-3 py-3">Requested</th>
                  <th className="px-3 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {pendingUsers.map((pendingUser) => {
                  const createdAt = pendingUser.createdAt
                    ? new Date(pendingUser.createdAt).toLocaleDateString()
                    : '—';
                  const isBusy = actionUserId === pendingUser.id;

                  return (
                    <tr key={pendingUser.id} className="border-b last:border-b-0 border-slate-200">
                      <td className="px-3 py-3 font-medium text-slate-900">{pendingUser.email}</td>
                      <td className="px-3 py-3 text-slate-600">{createdAt}</td>
                      <td className="px-3 py-3 text-right space-x-2">
                        <Button
                          size="sm"
                          onClick={() => handleDecision(pendingUser.id, 'approve')}
                          disabled={isBusy}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDecision(pendingUser.id, 'deny')}
                          disabled={isBusy}
                        >
                          Deny
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
