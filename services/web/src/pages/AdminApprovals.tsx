import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Inbox } from 'lucide-react';
import { PageHeader } from '@/components/custom/PageHeader';
import { Button } from '@/components/ui/button';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { formatDateOrFallback } from '@/lib/date';
import { useMessageToast } from '@/lib/toast';

type AdminUser = {
  id: string;
  email: string;
  name?: string;
  role?: string;
  status?: string;
  adminRequestStatus?: string;
  createdAt?: string;
  deniedAt?: string;
  adminRequestedAt?: string;
};

type ViewMode = 'users' | 'requests' | 'denied';
type UserRole = 'admin' | 'user';
type UserStatus = 'approved' | 'pending' | 'denied';

type EmptyStateProps = {
  title: string;
  description?: string;
  icon?: ReactNode;
};

function EmptyState({ title, description, icon }: EmptyStateProps) {
  return (
    <div className="surface-subtle mt-3 border-dashed px-4 py-3 text-sm text-muted-foreground">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-full bg-card p-1 text-muted-foreground ring-1 ring-inset ring-border/40">
          {icon}
        </div>
        <div>
          <p className="font-medium text-foreground">{title}</p>
          {description ? <p className="mt-1 text-muted-foreground">{description}</p> : null}
        </div>
      </div>
    </div>
  );
}

export function AdminApprovalsPage() {
  const { user } = useAuth();
  const [approvedUsers, setApprovedUsers] = useState<AdminUser[]>([]);
  const [pendingUsers, setPendingUsers] = useState<AdminUser[]>([]);
  const [deniedUsers, setDeniedUsers] = useState<AdminUser[]>([]);
  const [pendingAdminRequests, setPendingAdminRequests] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionUserId, setActionUserId] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>('requests');
  const [search, setSearch] = useState('');
  const [draftEdits, setDraftEdits] = useState<Record<string, { role: UserRole; status: UserStatus }>>({});
  const permissionMessage = user && user.role !== 'admin' ? 'You do not have permission to view this page.' : null;
  useMessageToast('error', 'admin-approvals-error', error);
  useMessageToast('info', 'admin-approvals-message', message);
  useMessageToast('error', 'admin-approvals-permission', permissionMessage);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [approved, pending, denied, adminRequests] = await Promise.all([
        defaultApi.listApprovedUsers(),
        defaultApi.listPendingUsers(),
        defaultApi.listDeniedUsers(),
        defaultApi.listPendingAdminRequests(),
      ]);
      setApprovedUsers((approved as { users?: AdminUser[] }).users ?? []);
      setPendingUsers((pending as { users?: AdminUser[] }).users ?? []);
      setDeniedUsers((denied as { users?: AdminUser[] }).users ?? []);
      setPendingAdminRequests((adminRequests as { users?: AdminUser[] }).users ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load admin data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const filterUsers = useCallback(
    (users: AdminUser[]) =>
      users.filter((entry) => {
        if (!search.trim()) return true;
        const query = search.trim().toLowerCase();
        const email = entry.email ?? '';
        const name = entry.name ?? '';
        return (
          email.toLowerCase().includes(query) ||
          name.toLowerCase().includes(query)
        );
      }),
    [search],
  );

  const filteredApprovedUsers = useMemo(
    () => filterUsers(approvedUsers),
    [approvedUsers, filterUsers],
  );
  const filteredPendingUsers = useMemo(
    () => filterUsers(pendingUsers),
    [pendingUsers, filterUsers],
  );
  const filteredDeniedUsers = useMemo(
    () => filterUsers(deniedUsers),
    [deniedUsers, filterUsers],
  );
  const filteredAdminRequests = useMemo(
    () => filterUsers(pendingAdminRequests),
    [pendingAdminRequests, filterUsers],
  );

  const updateDraft = (entry: AdminUser, updates: Partial<{ role: UserRole; status: UserStatus }>) => {
    setDraftEdits((current) => {
      const existing = current[entry.id] ?? {
        role: (entry.role ?? 'user') as UserRole,
        status: (entry.status ?? 'approved') as UserStatus,
      };
      return {
        ...current,
        [entry.id]: { ...existing, ...updates },
      };
    });
  };

  const clearDraft = (userId: string) => {
    setDraftEdits((current) => {
      if (!current[userId]) return current;
      const next = { ...current };
      delete next[userId];
      return next;
    });
  };

  const handleDecision = async (userId: string, decision: 'approve' | 'deny') => {
    setActionUserId(userId);
    setError(null);
    setMessage(null);
    try {
      if (decision === 'approve') {
        await defaultApi.approveUser(userId);
        setMessage('User approved. An approval email has been sent.');
        const approvedUser = pendingUsers.find((entry) => entry.id === userId);
        setPendingUsers((current) => current.filter((entry) => entry.id !== userId));
        if (approvedUser) {
          setApprovedUsers((current) => [{ ...approvedUser, status: 'approved' }, ...current]);
        }
      } else {
        await defaultApi.denyUser(userId);
        setMessage('User denied.');
        const deniedUser = pendingUsers.find((entry) => entry.id === userId);
        setPendingUsers((current) => current.filter((entry) => entry.id !== userId));
        if (deniedUser) {
          setDeniedUsers((current) => [{ ...deniedUser, status: 'denied' }, ...current]);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update user status.');
    } finally {
      setActionUserId(null);
    }
  };

  const handleUnblock = async (userId: string) => {
    setActionUserId(userId);
    setError(null);
    setMessage(null);
    try {
      await defaultApi.unblockUser(userId);
      setMessage('User unblocked and returned to pending approvals.');
      const unblockedUser = deniedUsers.find((entry) => entry.id === userId);
      setDeniedUsers((current) => current.filter((entry) => entry.id !== userId));
      if (unblockedUser) {
        setPendingUsers((current) => [{ ...unblockedUser, status: 'pending' }, ...current]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to unblock user.');
    } finally {
      setActionUserId(null);
    }
  };

  const handleAdminRequest = async (userId: string, decision: 'approve' | 'deny') => {
    setActionUserId(userId);
    setError(null);
    setMessage(null);
    try {
      if (decision === 'approve') {
        await defaultApi.approveAdminRequest(userId);
        setMessage('Admin request approved.');
        const updatedUser = pendingAdminRequests.find((entry) => entry.id === userId);
        setPendingAdminRequests((current) => current.filter((entry) => entry.id !== userId));
        if (updatedUser) {
          setApprovedUsers((current) => {
            const exists = current.some((entry) => entry.id === userId);
            if (!exists) {
              return [{ ...updatedUser, role: 'admin', adminRequestStatus: 'approved' }, ...current];
            }
            return current.map((entry) =>
              entry.id === userId ? { ...entry, role: 'admin', adminRequestStatus: 'approved' } : entry,
            );
          });
        }
      } else {
        await defaultApi.denyAdminRequest(userId);
        setMessage('Admin request denied.');
        setPendingAdminRequests((current) => current.filter((entry) => entry.id !== userId));
        setApprovedUsers((current) =>
          current.map((entry) =>
            entry.id === userId ? { ...entry, adminRequestStatus: 'denied' } : entry,
          ),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update admin request.');
    } finally {
      setActionUserId(null);
    }
  };

  const handleUpdateUser = async (entry: AdminUser) => {
    const currentRole = (entry.role ?? 'user') as UserRole;
    const currentStatus = (entry.status ?? 'approved') as UserStatus;
    const draft = draftEdits[entry.id] ?? { role: currentRole, status: currentStatus };
    const updates: Partial<{ role: UserRole; status: UserStatus }> = {};

    if (draft.role !== currentRole) {
      updates.role = draft.role;
    }
    if (draft.status !== currentStatus) {
      updates.status = draft.status;
    }
    if (Object.keys(updates).length === 0) {
      clearDraft(entry.id);
      return;
    }

    setActionUserId(entry.id);
    setError(null);
    setMessage(null);
    try {
      await defaultApi.updateUser(entry.id, updates);
      setMessage('User updated.');
      clearDraft(entry.id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update user.');
    } finally {
      setActionUserId(null);
    }
  };

  if (user?.role !== 'admin') {
    return (
      <>
        <PageHeader
          label="Admin"
          title="User access"
          description="Admin access is required to manage access requests."
        />
        <div className="mt-6" />
      </>
    );
  }

  return (
    <>
      <PageHeader
        label="Admin"
        title="User access"
        description="Manage users, access requests, and denied accounts."
      />

      <section className="surface-card mt-6 p-4 md:p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
          <div>
            <h2 className="text-section-title">Admin console</h2>
            <p className="m-0 text-muted-foreground">
              {loading ? 'Loading data…' : `${approvedUsers.length} users`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={view === 'users' ? 'default' : 'outline'} onClick={() => setView('users')}>
              Current users
            </Button>
            <Button size="sm" variant={view === 'requests' ? 'default' : 'outline'} onClick={() => setView('requests')}>
              Requests
            </Button>
            <Button size="sm" variant={view === 'denied' ? 'default' : 'outline'} onClick={() => setView('denied')}>
              Denied users
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <input
            type="search"
            placeholder="Search by email or name"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="field-input w-full md:max-w-xs"
          />
        </div>

        <div className="mt-4" />

        {loading ? (
          <div className="surface-subtle mt-4 px-3 py-3 font-semibold text-foreground">
            Loading data…
          </div>
        ) : view === 'users' ? (
          <div className="mt-4 overflow-auto">
            {filteredApprovedUsers.length === 0 ? (
              <EmptyState
                title="No users match this search."
                description="Try a different name or email to see results."
                icon={<Inbox className="h-4 w-4" />}
              />
            ) : (
              <table className="table-grid">
                <thead className="table-head">
                  <tr className="table-row">
                    <th className="px-3 py-3">Email</th>
                    <th className="px-3 py-3">Role</th>
                    <th className="px-3 py-3">Access</th>
                    <th className="px-3 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredApprovedUsers.map((entry) => {
                    const isSelf = user?.id === entry.id;
                    const currentRole = (entry.role ?? 'user') as UserRole;
                    const currentStatus = (entry.status ?? 'approved') as UserStatus;
                    const draft = draftEdits[entry.id] ?? { role: currentRole, status: currentStatus };
                    const isDirty = draft.role !== currentRole || draft.status !== currentStatus;
                    const isBusy = actionUserId === entry.id;

                    return (
                      <tr key={entry.id} className="table-row last:border-b-0">
                        <td className="px-3 py-3 font-medium text-foreground">{entry.email}</td>
                        <td className="px-3 py-3">
                          <select
                            value={draft.role}
                            onChange={(event) => updateDraft(entry, { role: event.target.value as UserRole })}
                            disabled={isSelf || isBusy}
                            className="field-input w-full min-w-[120px] rounded-md bg-card px-2 py-1"
                          >
                            <option value="admin">Admin</option>
                            <option value="user">User</option>
                          </select>
                        </td>
                        <td className="px-3 py-3">
                          <select
                            value={draft.status}
                            onChange={(event) => updateDraft(entry, { status: event.target.value as UserStatus })}
                            disabled={isSelf || isBusy}
                            className="field-input w-full min-w-[140px] rounded-md bg-card px-2 py-1"
                          >
                            <option value="approved">Approved</option>
                            <option value="pending">Pending</option>
                            <option value="denied">Denied</option>
                          </select>
                        </td>
                        <td className="px-3 py-3 text-right space-x-2">
                          {isSelf ? (
                            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Signed in</span>
                          ) : (
                            <Button
                              size="sm"
                              variant={isDirty ? 'default' : 'outline'}
                              disabled={!isDirty || isBusy}
                              onClick={() => handleUpdateUser(entry)}
                            >
                              Update
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        ) : view === 'requests' ? (
          <div className="mt-4 space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-foreground">Pending access approvals</h3>
              {filteredPendingUsers.length === 0 ? (
                <EmptyState
                  title="No pending access requests."
                  description="New access requests will appear here as they come in."
                  icon={<Inbox className="h-4 w-4" />}
                />
              ) : (
                <div className="mt-3 overflow-auto">
                  <table className="table-grid">
                    <thead className="table-head">
                      <tr className="table-row">
                        <th className="px-3 py-3">Email</th>
                        <th className="px-3 py-3">Requested</th>
                        <th className="px-3 py-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredPendingUsers.map((pendingUser) => {
                        const createdAt = formatDateOrFallback(pendingUser.createdAt);
                        const isBusy = actionUserId === pendingUser.id;

                        return (
                          <tr key={pendingUser.id} className="table-row last:border-b-0">
                            <td className="px-3 py-3 font-medium text-foreground">{pendingUser.email}</td>
                            <td className="px-3 py-3 text-muted-foreground">{createdAt}</td>
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
            </div>

            <div>
              <h3 className="text-lg font-semibold text-foreground">Pending admin requests</h3>
              {filteredAdminRequests.length === 0 ? (
                <EmptyState
                  title="No pending admin requests."
                  description="Admin requests will surface here for review."
                  icon={<Inbox className="h-4 w-4" />}
                />
              ) : (
                <div className="mt-3 overflow-auto">
                  <table className="table-grid">
                    <thead className="table-head">
                      <tr className="table-row">
                        <th className="px-3 py-3">Email</th>
                        <th className="px-3 py-3">Requested</th>
                        <th className="px-3 py-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAdminRequests.map((pendingUser) => {
                        const requestedAt = formatDateOrFallback(pendingUser.adminRequestedAt);
                        const isBusy = actionUserId === pendingUser.id;

                        return (
                          <tr key={pendingUser.id} className="table-row last:border-b-0">
                            <td className="px-3 py-3 font-medium text-foreground">{pendingUser.email}</td>
                            <td className="px-3 py-3 text-muted-foreground">{requestedAt}</td>
                            <td className="px-3 py-3 text-right space-x-2">
                              <Button
                                size="sm"
                                onClick={() => handleAdminRequest(pendingUser.id, 'approve')}
                                disabled={isBusy}
                              >
                                Approve
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleAdminRequest(pendingUser.id, 'deny')}
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
            </div>
          </div>
        ) : (
          <div className="mt-4 overflow-auto">
            {filteredDeniedUsers.length === 0 ? (
              <EmptyState
                title="No denied users."
                description="Denied accounts will be listed here."
                icon={<Inbox className="h-4 w-4" />}
              />
            ) : (
              <table className="table-grid">
                <thead className="table-head">
                  <tr className="table-row">
                    <th className="px-3 py-3">Email</th>
                    <th className="px-3 py-3">Denied</th>
                    <th className="px-3 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDeniedUsers.map((entry) => {
                    const deniedAt = formatDateOrFallback(entry.deniedAt);
                    const isBusy = actionUserId === entry.id;

                    return (
                      <tr key={entry.id} className="table-row last:border-b-0">
                        <td className="px-3 py-3 font-medium text-foreground">{entry.email}</td>
                        <td className="px-3 py-3 text-muted-foreground">{deniedAt}</td>
                        <td className="px-3 py-3 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleUnblock(entry.id)}
                            disabled={isBusy}
                          >
                            Unblock
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>
    </>
  );
}
