import config from '../config.js';
import { databaseApiClient } from '../clients/databaseApi.js';
import * as mockData from '../mockData.js';
import type { Patient } from '../api/openapi-client/models/index.js';
import { tokenService } from './tokenService.js';

export interface CaseCreationResult {
  created: boolean;
  caseRecord: {
    caseId: string;
    patientId: string;
    cCaseId?: string;
    status: string;
    caseToken?: string | null;
  };
  patient: Patient | null;
  chariteCase?: {
    cCaseId: string;
    firstName: string;
    lastName: string;
    birthDate: Date;
  };
}

class PatientService {
  async listPatients(): Promise<Patient[]> {
    if (config.useMockData) {
      return mockData.listPatients();
    }

    try {
      const result = await databaseApiClient.getPatients();
      return result.patients.map(p => ({
        ...p,
        birthDate: new Date(p.birthDate),
      }));
    } catch (error) {
      console.error('Error fetching patients from API:', error);
      throw new Error('Failed to fetch patients');
    }
  }

  async getPatient(patientId: string): Promise<Patient | undefined> {
    if (config.useMockData) {
      return mockData.findPatient(patientId);
    }

    try {
      const patient = await databaseApiClient.getPatient(patientId);
      return {
        ...patient,
        birthDate: new Date(patient.birthDate),
      };
    } catch (error) {
      console.error(`Error fetching patient ${patientId}:`, error);
      return undefined;
    }
  }

  async getPatientCases(patientId: string) {
    if (config.useMockData) {
      return mockData.casesForPatient(patientId);
    }

    try {
      const result = await databaseApiClient.getPatientCases(patientId);
      return result.Cases;
    } catch (error) {
      console.error(`Error fetching cases for patient ${patientId}:`, error);
      throw new Error('Failed to fetch patient cases');
    }
  }
}

class CaseService {
  async listCases() {
    if (config.useMockData) {
      return mockData.listCases();
    }

    throw new Error('List all cases not implemented for real API');
  }

  async getCase(caseId: string) {
    if (config.useMockData) {
      return mockData.findCase(caseId);
    }

    try {
      return await databaseApiClient.getCase(caseId);
    } catch (error) {
      console.error(`Error fetching case ${caseId}:`, error);
      return undefined;
    }
  }

  async createCaseFromCharite(cCaseId: string): Promise<CaseCreationResult | undefined> {
    if (config.useMockData) {
      return mockData.createCaseFromCharite(cCaseId);
    }

    try {
      const chariteCase = mockData.findChariteCase(cCaseId);
      if (!chariteCase) {
        return undefined;
      }

      const searchResult = await databaseApiClient.getPatients({
        firstname: chariteCase.firstName,
        lastname: chariteCase.lastName
      });

      let patient: Patient;
      
      if (searchResult.patients.length > 0) {
        // Patient found - use the first match
        patient = {
          ...searchResult.patients[0],
          birthDate: new Date(searchResult.patients[0].birthDate),
        };
      } else {
        // 3. Create patient if not found
        const newPatient = await databaseApiClient.createPatient({
          chariteId: cCaseId, // Using cCaseId as chariteId
          firstName: chariteCase.firstName,
          lastName: chariteCase.lastName,
          sex: chariteCase.sex ?? 'other', // Use sex from ChariteCase or default to 'other'
          birthDate: chariteCase.birthDate,
          weight: chariteCase.weight ?? 0, // Use weight from ChariteCase or default to 0
        });
        patient = {
          ...newPatient,
          birthDate: new Date(newPatient.birthDate),
        };
      }

      // 4. Check if case already exists with this cCaseId
      const patientCases = await databaseApiClient.getPatientCases(patient.patientId);
      const existingCase = patientCases.Cases.find((c) => {
        return c.status === 'active';
      });

      if (existingCase) {
        // Generate a new token for the existing case
        const caseToken = tokenService.generateCaseToken(
          existingCase.caseId,
          existingCase.patientId
        );
        
        return {
          created: false,
          caseRecord: {
            caseId: existingCase.caseId,
            patientId: existingCase.patientId,
            cCaseId,
            status: existingCase.status,
            caseToken,
          },
          patient,
          chariteCase,
        };
      }

      // 5. Create new case
      const newCase = await databaseApiClient.createCase({
        status: 'active',
        patientId: patient.patientId,
        devices: [],
        wearables: [],
        contexts: [],
      });

      // Generate secure case token
      const caseToken = tokenService.generateCaseToken(
        newCase.caseId,
        newCase.patientId
      );

      return {
        created: true,
        caseRecord: {
          caseId: newCase.caseId,
          patientId: newCase.patientId,
          cCaseId,
          status: newCase.status,
          caseToken,
        },
        patient,
        chariteCase,
      };
    } catch (error) {
      console.error('Error creating case from Charité:', error);
      throw error;
    }
  }

  async verifyCaseToken(caseToken: string) {
    if (config.useMockData) {
      return mockData.verifyCaseToken(caseToken);
    }

    try {
      // Verify and decode the token
      const tokenPayload = tokenService.verifyCaseToken(caseToken);
      if (!tokenPayload) {
        return undefined;
      }
      
      // Fetch the case using the caseId from token
      const caseRecord = await databaseApiClient.getCase(tokenPayload.caseId);
      if (!caseRecord) {
        return undefined;
      }

      // Fetch the patient
      const patient = await databaseApiClient.getPatient(caseRecord.patientId);
      if (!patient) {
        return undefined;
      }

      // Build patient verifier using same logic as mock
      const patientVerifier = mockData.buildPatientVerifier({
        ...patient,
        birthDate: new Date(patient.birthDate),
      });

      return {
        caseRecord: {
          caseId: caseRecord.caseId,
          patientId: caseRecord.patientId,
          status: caseRecord.status,
          caseToken,
        },
        patientVerifier,
      };
    } catch (error) {
      console.error('Error verifying case token:', error);
      return undefined;
    }
  }
}

class ChariteCaseService {
  async findChariteCase(cCaseId: string) {
    // Using mock data for both modes until a Charité API is available
    return mockData.findChariteCase(cCaseId);
  }
}

export const patientService = new PatientService();
export const caseService = new CaseService();
export const chariteCaseService = new ChariteCaseService();