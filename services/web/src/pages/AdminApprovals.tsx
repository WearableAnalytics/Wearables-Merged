import { useCallback, useEffect, useMemo, useState } from 'react';
import type { AccessRequestType, NonAdminRole } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { defaultApi } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { isAdminUser } from '@/lib/userAccess';
import { useMessageToast } from '@/lib/toast';
import { AdminApprovalsDeniedTable } from './admin-approvals/components/AdminApprovalsDeniedTable';
import { AdminApprovalsRequestsView } from './admin-approvals/components/AdminApprovalsRequestsView';
import { AdminApprovalsUsersTable } from './admin-approvals/components/AdminApprovalsUsersTable';
import { AdminApprovalsViewControls } from './admin-approvals/components/AdminApprovalsViewControls';
import type {
  AccessProfile,
  AdminUser,
  UserDraft,
  UserDraftEdits,
  UserStatus,
  ViewMode,
} from './admin-approvals/components/types';

const toAccessProfile = (entry: AdminUser): AccessProfile => {
  if (entry.isAdmin) return 'admin';
  const roles = new Set(entry.roles ?? []);
  const hasPractitioner = roles.has('practitioner');
  const hasResearcher = roles.has('researcher');

  if (hasPractitioner && hasResearcher) return 'practitioner_researcher';
  if (hasResearcher) return 'researcher';
  return 'practitioner';
};

const toProfilePayload = (profile: AccessProfile): { isAdmin: boolean; roles: NonAdminRole[] } => {
  switch (profile) {
    case 'admin':
      return { isAdmin: true, roles: [] };
    case 'researcher':
      return { isAdmin: false, roles: ['researcher'] };
    case 'practitioner_researcher':
      return { isAdmin: false, roles: ['practitioner', 'researcher'] };
    case 'practitioner':
    default:
      return { isAdmin: false, roles: ['practitioner'] };
  }
};

export function AdminApprovalsPage() {
  const { user } = useAuth();
  const [approvedUsers, setApprovedUsers] = useState<AdminUser[]>([]);
  const [pendingUsers, setPendingUsers] = useState<AdminUser[]>([]);
  const [deniedUsers, setDeniedUsers] = useState<AdminUser[]>([]);
  const [pendingAccessRequests, setPendingAccessRequests] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [actionUserId, setActionUserId] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>('requests');
  const [search, setSearch] = useState('');
  const [draftEdits, setDraftEdits] = useState<UserDraftEdits>({});
  const permissionMessage = user && !isAdminUser(user) ? 'You do not have permission to view this page.' : null;

  useMessageToast('error', 'admin-approvals-error', error);
  useMessageToast('info', 'admin-approvals-message', message);
  useMessageToast('error', 'admin-approvals-permission', permissionMessage);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [approved, pending, denied, accessRequests] = await Promise.all([
        defaultApi.listApprovedUsers(),
        defaultApi.listPendingUsers(),
        defaultApi.listDeniedUsers(),
        defaultApi.listPendingAccessRequests(),
      ]);
      setApprovedUsers((approved as { users?: AdminUser[] }).users ?? []);
      setPendingUsers((pending as { users?: AdminUser[] }).users ?? []);
      setDeniedUsers((denied as { users?: AdminUser[] }).users ?? []);
      setPendingAccessRequests((accessRequests as { users?: AdminUser[] }).users ?? []);
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
  const filteredAccessRequests = useMemo(() => filterUsers(pendingAccessRequests), [pendingAccessRequests, filterUsers]);

  const updateDraft = (entry: AdminUser, updates: Partial<UserDraft>) => {
    setDraftEdits((current) => {
      const existing = current[entry.id] ?? {
        accessProfile: toAccessProfile(entry),
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
      } else {
        await defaultApi.denyUser(userId);
        setMessage('User denied.');
      }
      await loadData();
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
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to unblock user.');
    } finally {
      setActionUserId(null);
    }
  };

  const handleAccessRequest = async (
    userId: string,
    requestType: AccessRequestType,
    decision: 'approve' | 'deny',
  ) => {
    setActionUserId(userId);
    setError(null);
    setMessage(null);
    try {
      await defaultApi.reviewAccessRequest(
        userId,
        requestType,
        decision === 'approve' ? 'approved' : 'denied',
      );
      setMessage(`${requestType.charAt(0).toUpperCase() + requestType.slice(1)} request ${decision}d.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update access request.');
    } finally {
      setActionUserId(null);
    }
  };

  const handleUpdateUser = async (entry: AdminUser) => {
    const currentAccessProfile = toAccessProfile(entry);
    const currentStatus = (entry.status ?? 'approved') as UserStatus;
    const draft = draftEdits[entry.id] ?? { accessProfile: currentAccessProfile, status: currentStatus };

    const profilePayload = toProfilePayload(draft.accessProfile);
    const currentProfilePayload = toProfilePayload(currentAccessProfile);
    const rolesDirty =
      profilePayload.isAdmin !== currentProfilePayload.isAdmin ||
      profilePayload.roles.join('|') !== currentProfilePayload.roles.join('|');
    const statusDirty = draft.status !== currentStatus;

    if (!rolesDirty && !statusDirty) {
      clearDraft(entry.id);
      return;
    }

    setActionUserId(entry.id);
    setError(null);
    setMessage(null);
    try {
      await defaultApi.updateUser(entry.id, {
        isAdmin: profilePayload.isAdmin,
        roles: profilePayload.roles,
        status: statusDirty ? draft.status : undefined,
      });
      setMessage('User updated.');
      clearDraft(entry.id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update user.');
    } finally {
      setActionUserId(null);
    }
  };

  if (!isAdminUser(user)) {
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
            pendingAccessRequests={filteredAccessRequests}
            actionUserId={actionUserId}
            onDecision={(userId, decision) => {
              void handleDecision(userId, decision);
            }}
            onAccessRequest={(userId, requestType, decision) => {
              void handleAccessRequest(userId, requestType, decision);
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
