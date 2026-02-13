import { useCallback, useEffect, useMemo, useState } from 'react';
import { PageHeader } from '@/components/custom/PageHeader';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { useMessageToast } from '@/lib/toast';
import { AdminApprovalsDeniedTable } from './admin-approvals/components/AdminApprovalsDeniedTable';
import { AdminApprovalsRequestsView } from './admin-approvals/components/AdminApprovalsRequestsView';
import { AdminApprovalsUsersTable } from './admin-approvals/components/AdminApprovalsUsersTable';
import { AdminApprovalsViewControls } from './admin-approvals/components/AdminApprovalsViewControls';
import type { AdminUser, UserDraft, UserDraftEdits, UserRole, UserStatus, ViewMode } from './admin-approvals/components/types';

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
  const [draftEdits, setDraftEdits] = useState<UserDraftEdits>({});
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
        return email.toLowerCase().includes(query) || name.toLowerCase().includes(query);
      }),
    [search],
  );

  const filteredApprovedUsers = useMemo(() => filterUsers(approvedUsers), [approvedUsers, filterUsers]);
  const filteredPendingUsers = useMemo(() => filterUsers(pendingUsers), [pendingUsers, filterUsers]);
  const filteredDeniedUsers = useMemo(() => filterUsers(deniedUsers), [deniedUsers, filterUsers]);
  const filteredAdminRequests = useMemo(() => filterUsers(pendingAdminRequests), [pendingAdminRequests, filterUsers]);

  const updateDraft = (entry: AdminUser, updates: Partial<UserDraft>) => {
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
          current.map((entry) => (entry.id === userId ? { ...entry, adminRequestStatus: 'denied' } : entry)),
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
        <AdminApprovalsViewControls
          loading={loading}
          approvedUsersCount={approvedUsers.length}
          view={view}
          onViewChange={setView}
          search={search}
          onSearchChange={setSearch}
        />

        <div className="mt-4" />

        {loading ? (
          <div className="surface-subtle mt-4 px-3 py-3 font-semibold text-foreground">Loading data…</div>
        ) : view === 'users' ? (
          <AdminApprovalsUsersTable
            users={filteredApprovedUsers}
            currentUserId={user?.id}
            actionUserId={actionUserId}
            draftEdits={draftEdits}
            onDraftUpdate={updateDraft}
            onUpdate={(entry) => {
              void handleUpdateUser(entry);
            }}
          />
        ) : view === 'requests' ? (
          <AdminApprovalsRequestsView
            pendingUsers={filteredPendingUsers}
            pendingAdminRequests={filteredAdminRequests}
            actionUserId={actionUserId}
            onDecision={(userId, decision) => {
              void handleDecision(userId, decision);
            }}
            onAdminRequest={(userId, decision) => {
              void handleAdminRequest(userId, decision);
            }}
          />
        ) : (
          <AdminApprovalsDeniedTable
            users={filteredDeniedUsers}
            actionUserId={actionUserId}
            onUnblock={(userId) => {
              void handleUnblock(userId);
            }}
          />
        )}
      </section>
    </>
  );
}
