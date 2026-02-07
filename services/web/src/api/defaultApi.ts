import { Configuration, CasesApi, CharitCasesApi, PatientsApi } from './openapi-client';

// Shared configuration for all generated API classes.
export const API_BASE_PATH = import.meta.env.VITE_API_BASE_URL ?? '/api';

const sharedConfig = new Configuration({
  basePath: API_BASE_PATH,
  credentials: 'include',
});

export class DefaultApi {
  private casesApi = new CasesApi(sharedConfig);
  private charitCasesApi = new CharitCasesApi(sharedConfig);
  private patientsApi = new PatientsApi(sharedConfig);

  // Auth (custom)
  login = async (email: string) => {
    const response = await fetch(`${API_BASE_PATH}/login`, {
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

  register = async (email: string) => {
    const response = await fetch(`${API_BASE_PATH}/register`, {
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
    const response = await fetch(`${API_BASE_PATH}/me`, {
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
    const response = await fetch(`${API_BASE_PATH}/logout`, {
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
    const response = await fetch(`${API_BASE_PATH}/request-admin`, {
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

  listPendingUsers = async () => {
    const response = await fetch(`${API_BASE_PATH}/admin/pending-users`, {
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
    const response = await fetch(`${API_BASE_PATH}/admin/approved-users`, {
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
    const response = await fetch(`${API_BASE_PATH}/admin/denied-users`, {
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

  listPendingAdminRequests = async () => {
    const response = await fetch(`${API_BASE_PATH}/admin/pending-admin-requests`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to load admin requests.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  approveUser = async (userId: string) => {
    const response = await fetch(`${API_BASE_PATH}/admin/users/${userId}/approve`, {
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
    const response = await fetch(`${API_BASE_PATH}/admin/users/${userId}/deny`, {
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
    const response = await fetch(`${API_BASE_PATH}/admin/users/${userId}/unblock`, {
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

  approveAdminRequest = async (userId: string) => {
    const response = await fetch(`${API_BASE_PATH}/admin/users/${userId}/approve-admin`, {
      method: 'POST',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to approve admin request.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  denyAdminRequest = async (userId: string) => {
    const response = await fetch(`${API_BASE_PATH}/admin/users/${userId}/deny-admin`, {
      method: 'POST',
      credentials: 'include',
    });
    const data = await response.json().catch(() => ({} as Record<string, unknown>));

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? 'Unable to deny admin request.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  updateUser = async (
    userId: string,
    updates: { role?: 'admin' | 'user'; status?: 'approved' | 'pending' | 'denied' },
  ) => {
    const response = await fetch(`${API_BASE_PATH}/admin/users/${userId}`, {
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
  casesCaseIdGet = this.casesApi.casesCaseIdGet.bind(this.casesApi);
  casesFromChariteCasePost = this.casesApi.casesFromChariteCasePost.bind(this.casesApi);
  casesGet = this.casesApi.casesGet.bind(this.casesApi);
  casesVerifyTokenPost = this.casesApi.casesVerifyTokenPost.bind(this.casesApi);

  // Charité cases
  chariteCasesCCaseIdGet = this.charitCasesApi.chariteCasesCCaseIdGet.bind(this.charitCasesApi);

  // Patients
  patientsGet = this.patientsApi.patientsGet.bind(this.patientsApi);
  patientsPatientIdCasesGet = this.patientsApi.patientsPatientIdCasesGet.bind(this.patientsApi);
  patientsPatientIdGet = this.patientsApi.patientsPatientIdGet.bind(this.patientsApi);
}

// Singleton instance that mirrors the prior "defaultApi" pattern.
export const defaultApi = new DefaultApi();
