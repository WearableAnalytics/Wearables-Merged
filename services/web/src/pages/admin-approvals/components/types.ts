export type NonAdminRole = 'practitioner' | 'researcher';
export type AccessRequestType = 'admin' | NonAdminRole;
export type RequestStatus = 'none' | 'pending' | 'approved' | 'denied';

export type AdminUser = {
  id: string;
  email: string;
  name?: string;
  isAdmin?: boolean;
  roles?: string[];
  status?: string;
  adminRequestStatus?: string;
  roleRequestStatuses?: Partial<Record<NonAdminRole, RequestStatus>>;
  createdAt?: string;
  deniedAt?: string;
  requestType?: AccessRequestType;
  requestedAt?: string;
};

export type ViewMode = 'users' | 'requests' | 'denied';
export type AccessProfile = 'admin' | 'practitioner' | 'researcher' | 'practitioner_researcher';
export type UserStatus = 'approved' | 'pending' | 'denied';

export type UserDraft = {
  accessProfile: AccessProfile;
  status: UserStatus;
};

export type UserDraftEdits = Record<string, UserDraft>;
