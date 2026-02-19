import { Configuration, CasesApi, HospitalCasesApi, PatientsApi } from './openapi-client';
import type { Middleware } from './openapi-client';
import { dispatchSessionExpiredEvent } from '@/lib/authSession';

const normalizeApiBasePath = (rawBasePath: string) => {
  const trimmed = rawBasePath.replace(/\/$/, '') || '/api';

  if (!import.meta.env.DEV) {
    return trimmed;
  }

  try {
    const url = new URL(trimmed);
    const isLocalHost = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
    if (isLocalHost) {
      return url.pathname.replace(/\/$/, '') || '/api';
    }
  } catch {
    return trimmed;
  }

  return trimmed;
};

// Shared configuration for all generated API classes.
export const API_BASE_PATH = normalizeApiBasePath(import.meta.env.VITE_API_BASE_URL ?? '/api');

export type NonAdminRole = 'practitioner' | 'researcher';
export type AccessRequestType = 'admin' | NonAdminRole;

export const isDirectAuthResponse = (data: unknown): boolean =>
  Boolean(
    data &&
      typeof data === 'object' &&
      'authenticated' in data &&
      (data as { authenticated?: unknown }).authenticated === true,
  );

const handleUnauthorizedStatus = (status: number) => {
  if (status === 401) {
    dispatchSessionExpiredEvent();
  }
};

const fetchWithAuthHandling: typeof fetch = async (input, init) => {
  const response = await fetch(input, init);
  handleUnauthorizedStatus(response.status);
  return response;
};

const authMiddleware: Middleware = {
  post: async ({ response }) => {
    handleUnauthorizedStatus(response.status);
    return response;
  },
};

const sharedConfig = new Configuration({
  basePath: API_BASE_PATH,
  credentials: 'include',
  middleware: [authMiddleware],
});

export class DefaultApi {
  private casesApi = new CasesApi(sharedConfig);
  private hospitalCasesApi = new HospitalCasesApi(sharedConfig);
  private patientsApi = new PatientsApi(sharedConfig);

  // Auth (custom)
  login = async (email: string) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email }),
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const errorCode = (data && (data.code ?? data.errorCode)) as string | undefined;
      const message =
        errorCode === 'ACCOUNT_DENIED'
          ? 'Unable to log in. Please contact support.'
          : (data && (data.message ?? data.error)) ??
            (response.status === 404
              ? 'This email is not registered. Please sign up first.'
              : 'Unable to log in.');
      const error = new Error(message) as Error & {
        status?: number;
        redirectToSignup?: boolean;
        code?: string;
      };
      error.status = response.status;
      error.code = (data && (data.code ?? data.errorCode)) as string | undefined;
      if ((data as { redirectToSignup?: boolean }).redirectToSignup) {
        error.redirectToSignup = true;
      }
      throw error;
    }

    return data;
  };

  register = async (email: string, role: NonAdminRole) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, role }),
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const errorCode = (data && (data.code ?? data.errorCode)) as string | undefined;
      const message =
        errorCode === 'ACCOUNT_DENIED'
          ? 'Unable to submit request. Please contact support.'
          : (data && (data.message ?? data.error)) ??
            (response.status === 409
              ? 'This email is already registered. Please log in instead.'
              : 'Unable to register.');
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  me = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/me`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (response.status === 401) {
      return null;
    }

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to load session.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return (data as { user?: unknown }).user ?? null;
  };

  logout = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/logout`, {
      method: 'POST',
      credentials: 'include',
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({} as Record<string, unknown>));
      const message = (data && (data.message ?? data.error)) ?? 'Unable to log out.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return response.json().catch(() => ({} as Record<string, unknown>));
  };

  requestAdminAccess = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/request-admin`, {
      method: 'POST',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to request admin access.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  requestRoleAccess = async (role: NonAdminRole) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/request-role`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ role }),
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to request role access.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  getResearcherApiAccessToken = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/researcher/api-access-token`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to load API access token.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    const apiAccessToken = (data as { apiAccessToken?: unknown }).apiAccessToken;
    if (typeof apiAccessToken !== 'string' || !apiAccessToken) {
      throw new Error('Invalid API access token response.');
    }

    return { apiAccessToken };
  };

  listPendingUsers = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/pending-users`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to load pending users.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  listApprovedUsers = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/approved-users`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to load users.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  listDeniedUsers = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/denied-users`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to load denied users.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  listPendingAccessRequests = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/pending-access-requests`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to load access requests.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  approveUser = async (userId: string) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/users/${userId}/approve`, {
      method: 'POST',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to approve user.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  denyUser = async (userId: string) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/users/${userId}/deny`, {
      method: 'POST',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to deny user.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  unblockUser = async (userId: string) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/users/${userId}/unblock`, {
      method: 'POST',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to unblock user.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  reviewAccessRequest = async (
    userId: string,
    requestType: AccessRequestType,
    decision: 'approved' | 'denied',
  ) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/users/${userId}/review-request`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ requestType, decision }),
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to review request.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  updateUser = async (
    userId: string,
    updates: {
      isAdmin?: boolean;
      roles?: NonAdminRole[];
      status?: 'approved' | 'pending' | 'denied';
    },
  ) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/admin/users/${userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(updates),
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to update user.';
      const error = new Error(message) as Error & { status?: number; code?: string };
      error.status = response.status;
      error.code = (data && (data.code ?? data.errorCode)) as string | undefined;
      throw error;
    }

    return data;
  };

  // Cases
  casesCaseIdGetRaw = this.casesApi.casesCaseIdGetRaw.bind(this.casesApi);
  casesCaseIdGet = this.casesApi.casesCaseIdGet.bind(this.casesApi);
  casesFromHospitalCasePost = this.casesApi.casesFromHospitalCasePost.bind(this.casesApi);
  casesGet = this.casesApi.casesGet.bind(this.casesApi);
  casesVerifyTokenPost = this.casesApi.casesVerifyTokenPost.bind(this.casesApi);

  // Hospital cases
  hospitalCasesHospitalCaseIdGet = this.hospitalCasesApi.hospitalCasesHospitalCaseIdGet.bind(this.hospitalCasesApi);

  // Patients
  patientsGet = this.patientsApi.patientsGet.bind(this.patientsApi);
  patientsPatientIdCasesGet = this.patientsApi.patientsPatientIdCasesGet.bind(this.patientsApi);
  patientsPatientIdGetRaw = this.patientsApi.patientsPatientIdGetRaw.bind(this.patientsApi);
  patientsPatientIdGet = this.patientsApi.patientsPatientIdGet.bind(this.patientsApi);
}

// Singleton instance that mirrors the prior "defaultApi" pattern.
export const defaultApi = new DefaultApi();
