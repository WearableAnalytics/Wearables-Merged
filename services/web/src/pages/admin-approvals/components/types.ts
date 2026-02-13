export type AdminUser = {
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

export type ViewMode = 'users' | 'requests' | 'denied';
export type UserRole = 'admin' | 'user';
export type UserStatus = 'approved' | 'pending' | 'denied';

export type UserDraft = {
  role: UserRole;
  status: UserStatus;
};

export type UserDraftEdits = Record<string, UserDraft>;
