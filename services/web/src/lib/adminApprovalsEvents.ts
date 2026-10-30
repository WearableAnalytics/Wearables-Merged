export const ADMIN_APPROVALS_UPDATED_EVENT = 'admin-approvals-updated';

export type AdminApprovalsUpdatedDetail = {
  openRequestsCount?: number;
};

export const dispatchAdminApprovalsUpdatedEvent = (detail?: AdminApprovalsUpdatedDetail) => {
  window.dispatchEvent(new CustomEvent<AdminApprovalsUpdatedDetail>(ADMIN_APPROVALS_UPDATED_EVENT, { detail }));
};
