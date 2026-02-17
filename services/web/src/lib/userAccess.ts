export type NonAdminRole = 'practitioner' | 'researcher';
export type AccessRequestStatus = 'none' | 'pending' | 'approved' | 'denied';

export type AuthUserLike = {
  isAdmin?: boolean;
  roles?: string[];
  adminRequestStatus?: AccessRequestStatus;
  roleRequestStatuses?: Partial<Record<NonAdminRole, AccessRequestStatus>>;
};

const normalizedRoleSet = new Set<NonAdminRole>(['practitioner', 'researcher']);

export const getNonAdminRoles = (user: AuthUserLike | null | undefined): NonAdminRole[] => {
  if (!user) return [];
  const fromArray = (user.roles ?? []).filter((role): role is NonAdminRole =>
    normalizedRoleSet.has(role as NonAdminRole),
  );

  if (fromArray.length > 0) {
    return Array.from(new Set(fromArray)).sort();
  }

  return [];
};

export const isAdminUser = (user: AuthUserLike | null | undefined): boolean =>
  Boolean(user?.isAdmin);

export const hasRole = (user: AuthUserLike | null | undefined, role: NonAdminRole): boolean =>
  getNonAdminRoles(user).includes(role);

export const canAccessPractitionerPages = (user: AuthUserLike | null | undefined): boolean =>
  isAdminUser(user) || hasRole(user, 'practitioner');

export const getDefaultAuthenticatedPath = (user: AuthUserLike | null | undefined): string =>
  canAccessPractitionerPages(user) ? '/overview' : '/account';

export const formatAccessLabel = (user: AuthUserLike | null | undefined): string => {
  if (isAdminUser(user)) {
    return 'Admin';
  }

  const roles = getNonAdminRoles(user);
  if (roles.length === 0) {
    return 'None';
  }
  if (roles.length === 2) {
    return 'Practitioner + Researcher';
  }

  return roles[0] === 'practitioner' ? 'Practitioner' : 'Researcher';
};

export const getRoleRequestStatus = (
  user: AuthUserLike | null | undefined,
  role: NonAdminRole,
): AccessRequestStatus => {
  const status = user?.roleRequestStatuses?.[role];
  return status ?? 'none';
};

export const getMissingNonAdminRole = (
  user: AuthUserLike | null | undefined,
): NonAdminRole | null => {
  if (!user || isAdminUser(user)) return null;

  const roles = getNonAdminRoles(user);
  if (roles.includes('practitioner') && !roles.includes('researcher')) return 'researcher';
  if (roles.includes('researcher') && !roles.includes('practitioner')) return 'practitioner';
  return null;
};
