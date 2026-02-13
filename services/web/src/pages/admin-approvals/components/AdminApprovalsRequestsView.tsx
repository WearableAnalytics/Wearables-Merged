import { Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatDateOrFallback } from '@/lib/date';
import { AdminApprovalsEmptyState } from './AdminApprovalsEmptyState';
import type { AdminUser } from './types';

type AdminApprovalsRequestsViewProps = {
  pendingUsers: AdminUser[];
  pendingAdminRequests: AdminUser[];
  actionUserId: string | null;
  onDecision: (userId: string, decision: 'approve' | 'deny') => void;
  onAdminRequest: (userId: string, decision: 'approve' | 'deny') => void;
};

export function AdminApprovalsRequestsView({
  pendingUsers,
  pendingAdminRequests,
  actionUserId,
  onDecision,
  onAdminRequest,
}: AdminApprovalsRequestsViewProps) {
  return (
    <div className="mt-4 space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-foreground">Pending access approvals</h3>
        {pendingUsers.length === 0 ? (
          <AdminApprovalsEmptyState
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
                {pendingUsers.map((pendingUser) => {
                  const createdAt = formatDateOrFallback(pendingUser.createdAt);
                  const isBusy = actionUserId === pendingUser.id;

                  return (
                    <tr key={pendingUser.id} className="table-row last:border-b-0">
                      <td className="px-3 py-3 font-medium text-foreground">{pendingUser.email}</td>
                      <td className="px-3 py-3 text-muted-foreground">{createdAt}</td>
                      <td className="space-x-2 px-3 py-3 text-right">
                        <Button size="sm" onClick={() => onDecision(pendingUser.id, 'approve')} disabled={isBusy}>
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onDecision(pendingUser.id, 'deny')}
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
        {pendingAdminRequests.length === 0 ? (
          <AdminApprovalsEmptyState
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
                {pendingAdminRequests.map((pendingUser) => {
                  const requestedAt = formatDateOrFallback(pendingUser.adminRequestedAt);
                  const isBusy = actionUserId === pendingUser.id;

                  return (
                    <tr key={pendingUser.id} className="table-row last:border-b-0">
                      <td className="px-3 py-3 font-medium text-foreground">{pendingUser.email}</td>
                      <td className="px-3 py-3 text-muted-foreground">{requestedAt}</td>
                      <td className="space-x-2 px-3 py-3 text-right">
                        <Button size="sm" onClick={() => onAdminRequest(pendingUser.id, 'approve')} disabled={isBusy}>
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onAdminRequest(pendingUser.id, 'deny')}
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
  );
}
