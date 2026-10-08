import config from '../config.js';

export interface Patient {
  id: string;
  charite_id?: string; // db_lord field
  hospital_id?: string; // optional alias used by some db_lord deployments
  name: string;
  sex?: string;
  dob?: string; // ISO date string from db_lord
  weight?: number;
  height?: number;
}

/** Payload for creating a patient. db_lord expects charite_id (UUID). */
export interface PatientBase {
  charite_id: string; // UUID string, required by db_lord
  name: string;
  sex?: string;
  dob?: string; // ISO date string
  weight?: number;
  height?: number;
}

export interface Case {
  id: string;
  status: string;
  patient_id: string;
  devices?: CaseDevice[];
  wearables?: CaseWearable[];
  contexts?: string[];
}

export interface CaseDevice {
  deviceId: string;
  assignedFrom: number;
  assignedTo?: number;
}

export interface CaseWearable {
  wearableId: string;
  assignedFrom: number;
  assignedTo?: number;
}

export interface PatientQueryParams {
  lastname?: string;
  firstname?: string;
  sex?: 'female' | 'male' | 'other';
  birthRangeStart?: string;
  birthRangeEnd?: string;
  weightRangeStart?: number;
  weightRangeEnd?: number;
}

/** Researcher export API token as stored by db_lord (only its hash is stored). */
export interface ApiTokenRecord {
  id: string;
  token_hint: string;
  owner_email: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  revoked_by: string | null;
}

export class DatabaseApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = 'DatabaseApiError';
  }
}

const LIST_PAGE_SIZE = 100;
const MAX_LIST_PAGES = 50;

class DatabaseApiClient {
  private baseUrl: string;
  private timeout: number;

  constructor() {
    this.baseUrl = config.databaseApi.baseUrl;
    this.timeout = config.databaseApi.timeout;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new DatabaseApiError(
          `Database API error: ${response.status} ${response.statusText} - ${errorBody}`,
          response.status,
        );
      }

      // db_lord answers deletes with 204 No Content.
      const text = await response.text();
      return (text ? JSON.parse(text) : undefined) as T;
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new Error(`Database API request timeout after ${this.timeout}ms`);
        }
        throw error;
      }
      throw new Error('Unknown error occurred');
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // Patient Operations
  async createPatient(patient: PatientBase): Promise<Patient> {
    return this.request<Patient>('/patients/', {
      method: 'POST',
      body: JSON.stringify(patient),
    });
  }

  async getPatients(params?: PatientQueryParams): Promise<Patient[]> {
    // db_lord filters: name__ilike, sex, dob__ge / dob__le. Weight is not a
    // server-side filter, so it is applied here.
    const queryParams = new URLSearchParams();
    const name = [params?.firstname, params?.lastname].filter(Boolean).join(' ');
    if (name) queryParams.set('name__ilike', `%${name}%`);
    if (params?.sex) queryParams.set('sex', params.sex);
    if (params?.birthRangeStart) queryParams.set('dob__ge', params.birthRangeStart);
    if (params?.birthRangeEnd) queryParams.set('dob__le', params.birthRangeEnd);

    const patients = await this.listAll<Patient>('/patients/', queryParams);
    return patients.filter(
      (patient) =>
        (params?.weightRangeStart === undefined ||
          (patient.weight !== undefined && patient.weight >= params.weightRangeStart)) &&
        (params?.weightRangeEnd === undefined ||
          (patient.weight !== undefined && patient.weight <= params.weightRangeEnd))
    );
  }

  async getPatient(patientId: string): Promise<Patient> {
    return this.request<Patient>(`/patients/${patientId}`);
  }

  // charite_id is immutable in db_lord; send only the fields that change.
  async updatePatient(
    patientId: string,
    patient: Partial<Omit<PatientBase, 'charite_id'>>
  ): Promise<void> {
    await this.request<void>(`/patients/${patientId}`, {
      method: 'PATCH',
      body: JSON.stringify(patient),
    });
  }

  async deletePatient(patientId: string): Promise<void> {
    await this.request<void>(`/patients/${patientId}`, {
      method: 'DELETE',
    });
  }

  async getPatientCases(patientId: string, status?: string): Promise<Case[]> {
    const query = status ? `?status=${status}` : '';
    return this.request<Case[]>(`/patients/${patientId}/cases${query}`);
  }

  // Case Operations
  // db_lord rejects unknown fields; devices, wearables and contexts are linked
  // through the /cases/{id}/devices|wearables|contexts/{itemId} endpoints.
  async createCase(caseData: { status: string; patient_id: string }): Promise<Case> {
    return this.request<Case>('/cases/', {
      method: 'POST',
      body: JSON.stringify(caseData),
    });
  }

  async getCase(caseId: string): Promise<Case> {
    return this.request<Case>(`/cases/${caseId}`);
  }

  async updateCase(caseId: string, caseData: { status?: string; patient_id?: string }): Promise<void> {
    await this.request<void>(`/cases/${caseId}`, {
      method: 'PATCH',
      body: JSON.stringify(caseData),
    });
  }

  async deleteCase(caseId: string): Promise<void> {
    await this.request<void>(`/cases/${caseId}`, {
      method: 'DELETE',
    });
  }

  async getCases(): Promise<Case[]> {
    return this.listAll<Case>('/cases/');
  }

  // Researcher export API tokens
  async createApiToken(token: {
    token_hash: string;
    token_hint: string;
    owner_email: string;
    name: string;
  }): Promise<ApiTokenRecord> {
    return this.request<ApiTokenRecord>('/api-tokens/', {
      method: 'POST',
      body: JSON.stringify(token),
    });
  }

  async listApiTokens(params: { ownerEmail?: string; includeRevoked?: boolean } = {}): Promise<ApiTokenRecord[]> {
    const query = new URLSearchParams();
    if (params.ownerEmail) query.set('owner_email', params.ownerEmail);
    if (params.includeRevoked) query.set('include_revoked', 'true');
    return this.request<ApiTokenRecord[]>(`/api-tokens/?${query}`);
  }

  /** The active token with this hash, or undefined if it is unknown or revoked. */
  async verifyApiToken(tokenHash: string): Promise<ApiTokenRecord | undefined> {
    try {
      return await this.request<ApiTokenRecord>('/api-tokens/verify', {
        method: 'POST',
        body: JSON.stringify({ token_hash: tokenHash }),
      });
    } catch (error) {
      if (error instanceof DatabaseApiError && error.status === 404) return undefined;
      throw error;
    }
  }

  async revokeApiToken(tokenId: string, revokedBy: string): Promise<ApiTokenRecord> {
    return this.request<ApiTokenRecord>(`/api-tokens/${encodeURIComponent(tokenId)}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ revoked_by: revokedBy }),
    });
  }

  /**
   * Reads every page of a db_lord list endpoint ({ items, next_page }).
   * Older db_lord images answered with a plain array; that still works.
   */
  private async listAll<T>(endpoint: string, params = new URLSearchParams()): Promise<T[]> {
    const items: T[] = [];
    let cursor: string | null = null;
    for (let page = 0; page < MAX_LIST_PAGES; page++) {
      const query = new URLSearchParams(params);
      query.set('size', String(LIST_PAGE_SIZE));
      if (cursor) query.set('cursor', cursor);

      const body = await this.request<T[] | { items: T[]; next_page: string | null }>(
        `${endpoint}?${query}`
      );
      if (Array.isArray(body)) return body;

      items.push(...body.items);
      cursor = body.next_page;
      if (!cursor) break;
    }
    return items;
  }
}

export const databaseApiClient = new DatabaseApiClient();
