import { Inbox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatDateOrFallback } from '@/lib/date';
import { AdminApprovalsEmptyState } from './AdminApprovalsEmptyState';
import type { AccessRequestType, AdminUser } from './types';

const requestLabel = (requestType: AccessRequestType) => {
  if (requestType === 'admin') return 'Admin';
  if (requestType === 'practitioner') return 'Practitioner';
  return 'Researcher';
};

const badgeClassName =
  'inline-flex items-center rounded-full border border-border bg-muted/40 px-2.5 py-1 text-xs font-semibold text-foreground';

type AdminApprovalsRequestsViewProps = {
  pendingUsers: AdminUser[];
  pendingAccessRequests: AdminUser[];
  actionUserId: string | null;
  onDecision: (userId: string, decision: 'approve' | 'deny') => void;
  onAccessRequest: (userId: string, requestType: AccessRequestType, decision: 'approve' | 'deny') => void;
};

export function AdminApprovalsRequestsView({
  pendingUsers,
  pendingAccessRequests,
  actionUserId,
  onDecision,
  onAccessRequest,
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
                  <th className="px-3 py-3">Initial role</th>
                  <th className="px-3 py-3">Requested</th>
                  <th className="px-3 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {pendingUsers.map((pendingUser) => {
                  const createdAt = formatDateOrFallback(pendingUser.createdAt);
                  const isBusy = actionUserId === pendingUser.id;
                  const initialRole = pendingUser.roles?.includes('researcher') ? 'Researcher' : 'Practitioner';

                  return (
                    <tr key={pendingUser.id} className="table-row last:border-b-0">
                      <td className="px-3 py-3 font-medium text-foreground">{pendingUser.email}</td>
                      <td className="px-3 py-3">
                        <span className={badgeClassName}>{initialRole}</span>
                      </td>
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
        <h3 className="text-lg font-semibold text-foreground">Pending role and admin requests</h3>
        {pendingAccessRequests.length === 0 ? (
          <AdminApprovalsEmptyState
            title="No pending role or admin requests."
            description="Additional access requests will appear here for review."
            icon={<Inbox className="h-4 w-4" />}
          />
        ) : (
          <div className="mt-3 overflow-auto">
            <table className="table-grid">
              <thead className="table-head">
                <tr className="table-row">
                  <th className="px-3 py-3">Email</th>
                  <th className="px-3 py-3">Request</th>
                  <th className="px-3 py-3">Requested</th>
                  <th className="px-3 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {pendingAccessRequests.map((pendingUser) => {
                  const requestedAt = formatDateOrFallback(pendingUser.requestedAt);
                  const isBusy = actionUserId === pendingUser.id;
                  const requestType = pendingUser.requestType;

                  if (!requestType) {
                    return null;
                  }

                  return (
                    <tr key={`${pendingUser.id}-${requestType}`} className="table-row last:border-b-0">
                      <td className="px-3 py-3 font-medium text-foreground">{pendingUser.email}</td>
                      <td className="px-3 py-3">
                        <span className={badgeClassName}>{requestLabel(requestType)}</span>
                      </td>
                      <td className="px-3 py-3 text-muted-foreground">{requestedAt}</td>
                      <td className="space-x-2 px-3 py-3 text-right">
                        <Button
                          size="sm"
                          onClick={() => onAccessRequest(pendingUser.id, requestType, 'approve')}
                          disabled={isBusy}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => onAccessRequest(pendingUser.id, requestType, 'deny')}
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
