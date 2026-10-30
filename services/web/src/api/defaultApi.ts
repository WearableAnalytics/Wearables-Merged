import {
  Configuration,
  CasesApi,
  HospitalCasesApi,
  PatientsApi,
} from './openapi-client';
import type { Middleware } from './openapi-client';
import { dispatchSessionExpiredEvent } from '@/lib/authSession';
import { appRuntimeConfig } from '@/config/runtimeConfig';

const normalizeApiBasePath = (rawBasePath: string) => {
  const trimmed = rawBasePath.replace(/\/$/, '') || '/';

  if (!import.meta.env.DEV) {
    return trimmed;
  }

  try {
    const url = new URL(trimmed);
    const isLocalHost =
      url.hostname === 'localhost' || url.hostname === '127.0.0.1';
    if (isLocalHost) {
      return url.pathname.replace(/\/$/, '') || '/';
    }
  } catch {
    return trimmed;
  }

  return trimmed;
};

// Shared configuration for all generated API classes.
export const API_BASE_PATH = normalizeApiBasePath(appRuntimeConfig.apiBaseUrl);

export type NonAdminRole = 'practitioner' | 'researcher';

/** Personal export API token. The token itself is only returned once, on creation. */
export type ApiToken = {
  id: string;
  name: string;
  token_hint: string;
  owner_email: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  revoked_by: string | null;
};

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
  login = async (email: string, password: string) => {
    return this.passwordRequest('/login', { email, password });
  };

  private passwordRequest = async (path: string, body: unknown) => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(
        data.error ?? 'The account operation was rejected.',
      ) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }
    return data;
  };

  changePassword = (
    currentPassword: string,
    newPassword: string,
    initial = false,
  ) =>
    this.passwordRequest(initial ? '/password/setup' : '/account/password', {
      currentPassword,
      newPassword,
    });

  createStaff = (details: {
    email: string;
    name?: string;
    isAdmin: boolean;
    roles: NonAdminRole[];
    temporaryPassword: string;
  }) => this.passwordRequest('/admin/users', details);

  resetStaffPassword = (
    id: string,
    expectedRevision: number,
    temporaryPassword: string,
  ) =>
    this.passwordRequest(
      `/admin/users/${encodeURIComponent(id)}/password-reset`,
      { expectedRevision, temporaryPassword },
    );

  me = async () => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}/me`, {
      method: 'GET',
      credentials: 'include',
    });
    const data = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);

    if (response.status === 401) {
      return null;
    }

    if (!response.ok) {
      const message =
        (data && (data.message ?? data.error)) ?? 'Unable to load session.';
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
      const data = await response
        .json()
        .catch(() => ({}) as Record<string, unknown>);
      const message =
        (data && (data.message ?? data.error)) ?? 'Unable to log out.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return response.json().catch(() => ({}) as Record<string, unknown>);
  };

  private apiTokenRequest = async <T>(
    path: string,
    fallbackMessage: string,
    init: RequestInit = {},
  ): Promise<T> => {
    const response = await fetchWithAuthHandling(`${API_BASE_PATH}${path}`, {
      credentials: 'include',
      ...init,
      headers: init.body ? { 'Content-Type': 'application/json' } : undefined,
    });
    const data = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);

    if (!response.ok) {
      const message = (data && (data.message ?? data.error)) ?? fallbackMessage;
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data as T;
  };

  listMyApiTokens = () =>
    this.apiTokenRequest<ApiToken[]>(
      '/researcher/api-tokens',
      'Unable to load your API tokens.',
    );

  createApiToken = (name: string) =>
    this.apiTokenRequest<ApiToken & { token: string }>(
      '/researcher/api-tokens',
      'Unable to create the API token.',
      {
        method: 'POST',
        body: JSON.stringify({ name }),
      },
    );

  revokeMyApiToken = (tokenId: string) =>
    this.apiTokenRequest<ApiToken>(
      `/researcher/api-tokens/${encodeURIComponent(tokenId)}/revoke`,
      'Unable to revoke the API token.',
      { method: 'POST' },
    );

  listAllApiTokens = () =>
    this.apiTokenRequest<ApiToken[]>(
      '/admin/api-tokens',
      'Unable to load API tokens.',
    );

  adminRevokeApiToken = (tokenId: string) =>
    this.apiTokenRequest<ApiToken>(
      `/admin/api-tokens/${encodeURIComponent(tokenId)}/revoke`,
      'Unable to revoke the API token.',
      { method: 'POST' },
    );

  listPendingUsers = async () => {
    const response = await fetchWithAuthHandling(
      `${API_BASE_PATH}/admin/pending-users`,
      {
        method: 'GET',
        credentials: 'include',
      },
    );
    const data = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);

    if (!response.ok) {
      const message =
        (data && (data.message ?? data.error)) ??
        'Unable to load pending users.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  listApprovedUsers = async () => {
    const response = await fetchWithAuthHandling(
      `${API_BASE_PATH}/admin/approved-users`,
      {
        method: 'GET',
        credentials: 'include',
      },
    );
    const data = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);

    if (!response.ok) {
      const message =
        (data && (data.message ?? data.error)) ?? 'Unable to load users.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  listDeniedUsers = async () => {
    const response = await fetchWithAuthHandling(
      `${API_BASE_PATH}/admin/denied-users`,
      {
        method: 'GET',
        credentials: 'include',
      },
    );
    const data = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);

    if (!response.ok) {
      const message =
        (data && (data.message ?? data.error)) ??
        'Unable to load denied users.';
      const error = new Error(message) as Error & { status?: number };
      error.status = response.status;
      throw error;
    }

    return data;
  };

  unblockUser = async (userId: string) => {
    const response = await fetchWithAuthHandling(
      `${API_BASE_PATH}/admin/users/${userId}/unblock`,
      {
        method: 'POST',
        credentials: 'include',
      },
    );
    const data = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);

    if (!response.ok) {
      const message =
        (data && (data.message ?? data.error)) ?? 'Unable to unblock user.';
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
    const response = await fetchWithAuthHandling(
      `${API_BASE_PATH}/admin/users/${userId}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(updates),
      },
    );
    const data = await response
      .json()
      .catch(() => ({}) as Record<string, unknown>);

    if (!response.ok) {
      const message =
        (data && (data.message ?? data.error)) ?? 'Unable to update user.';
      const error = new Error(message) as Error & {
        status?: number;
        code?: string;
      };
      error.status = response.status;
      error.code = (data && (data.code ?? data.errorCode)) as
        | string
        | undefined;
      throw error;
    }

    return data;
  };

  // Cases
  casesCaseIdGetRaw = this.casesApi.casesCaseIdGetRaw.bind(this.casesApi);
  casesCaseIdGet = this.casesApi.casesCaseIdGet.bind(this.casesApi);
  casesFromHospitalCasePost = this.casesApi.casesFromHospitalCasePost.bind(
    this.casesApi,
  );
  casesGet = this.casesApi.casesGet.bind(this.casesApi);
  casesVerifyTokenPost = this.casesApi.casesVerifyTokenPost.bind(this.casesApi);

  // Hospital cases
  hospitalCasesHospitalCaseIdGet =
    this.hospitalCasesApi.hospitalCasesHospitalCaseIdGet.bind(
      this.hospitalCasesApi,
    );

  // Patients
  patientsGet = this.patientsApi.patientsGet.bind(this.patientsApi);
  patientsPatientIdCasesGet = this.patientsApi.patientsPatientIdCasesGet.bind(
    this.patientsApi,
  );
  patientsPatientIdGetRaw = this.patientsApi.patientsPatientIdGetRaw.bind(
    this.patientsApi,
  );
  patientsPatientIdGet = this.patientsApi.patientsPatientIdGet.bind(
    this.patientsApi,
  );
}

// Singleton instance that mirrors the prior "defaultApi" pattern.
export const defaultApi = new DefaultApi();
