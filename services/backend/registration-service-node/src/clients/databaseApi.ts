import config from '../config.js';

export interface Patient {
  patientId: string;
  chariteId?: string;
  firstName: string;
  lastName: string;
  sex?: 'female' | 'male' | 'other';
  birthDate: Date;
  weight?: number;
}

export interface PatientBase {
  chariteId: string;
  firstName: string;
  lastName: string;
  sex: 'female' | 'male' | 'other';
  birthDate: Date;
  weight: number;
}

export interface Case {
  caseId: string;
  status: string;
  patientId: string;
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
      body: JSON.stringify({
        ...patient,
        birthDate: patient.birthDate.toISOString().split('T')[0],
      }),
    });
  }

  async getPatients(params?: PatientQueryParams): Promise<{ patients: Patient[] }> {
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
    
    return this.request<{ patients: Patient[] }>(endpoint);
  }

  async getPatient(patientId: string): Promise<Patient> {
    return this.request<Patient>(`/patients/${patientId}`);
  }

  async updatePatient(patientId: string, patient: PatientBase): Promise<void> {
    await this.request<void>(`/patients/${patientId}`, {
      method: 'PUT',
      body: JSON.stringify({
        ...patient,
        birthDate: patient.birthDate.toISOString().split('T')[0],
      }),
    });
  }

  async deletePatient(patientId: string): Promise<void> {
    await this.request<void>(`/patients/${patientId}`, {
      method: 'DELETE',
    });
  }

  async getPatientCases(patientId: string, status?: string): Promise<{ Cases: Case[] }> {
    const query = status ? `?status=${status}` : '';
    return this.request<{ Cases: Case[] }>(`/patients/${patientId}/cases${query}`);
  }

  // Case Operations
  async createCase(caseData: {
    status: string;
    patientId: string;
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
}

export const databaseApiClient = new DatabaseApiClient();
