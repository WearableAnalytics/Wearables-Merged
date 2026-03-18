import jwt from 'jsonwebtoken';
import config from '../config.js';

/**
 * Mint a short-lived service-account token so db_lord can verify that
 * calls originate from the BFF and not from an unauthenticated pod.
 * The token is signed with the same shared JWT_SECRET that db_lord validates.
 */
function mintServiceToken(): string {
  return jwt.sign(
    { sub: 'wearables-bff', service: true },
    config.jwtSecret,
    { expiresIn: '5m', algorithm: 'HS256' }
  );
}

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
          'Authorization': `Bearer ${mintServiceToken()}`,
          ...options.headers,
        },
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(
          `Database API error: ${response.status} ${response.statusText} - ${errorBody}`
        );
      }

      return await response.json();
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
    return this.request<Patient>('/patients', {
      method: 'POST',
      body: JSON.stringify(patient),
    });
  }

  async getPatients(params?: PatientQueryParams): Promise<Patient[]> {
    const queryParams = new URLSearchParams();
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          queryParams.append(key, String(value));
        }
      });
    }
    
    const query = queryParams.toString();
    const endpoint = query ? `/patients?${query}` : '/patients';
    
    return this.request<Patient[]>(endpoint);
  }

  async getPatient(patientId: string): Promise<Patient> {
    return this.request<Patient>(`/patients/${patientId}`);
  }

  async updatePatient(patientId: string, patient: PatientBase): Promise<void> {
    await this.request<void>(`/patients/${patientId}`, {
      method: 'PUT',
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
  async createCase(caseData: {
    status: string;
    patient_id: string;
    devices: CaseDevice[];
    wearables: CaseWearable[];
    contexts: string[];
  }): Promise<Case> {
    return this.request<Case>('/cases', {
      method: 'POST',
      body: JSON.stringify(caseData),
    });
  }

  async getCase(caseId: string): Promise<Case> {
    return this.request<Case>(`/cases/${caseId}`);
  }

  async updateCase(caseId: string, caseData: {
    status: string;
    patientId: string;
    devices: CaseDevice[];
    wearables: CaseWearable[];
    contexts: string[];
  }): Promise<void> {
    await this.request<void>(`/cases/${caseId}`, {
      method: 'PUT',
      body: JSON.stringify(caseData),
    });
  }

  async deleteCase(caseId: string): Promise<void> {
    await this.request<void>(`/cases/${caseId}`, {
      method: 'DELETE',
    });
  }

  async getCases(): Promise<Case[]> {
    return this.request<Case[]>('/cases');
  }
}

export const databaseApiClient = new DatabaseApiClient();
