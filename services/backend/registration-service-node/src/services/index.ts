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
      const patients = await databaseApiClient.getPatients();
      return patients.map(p => ({
        patientId: p.id,
        firstName: p.name.split(' ')[0] || '',
        lastName: p.name.split(' ').slice(1).join(' ') || '',
        birthDate: p.dob ? new Date(p.dob) : new Date(),
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
        patientId: patient.id,
        firstName: patient.name.split(' ')[0] || '',
        lastName: patient.name.split(' ').slice(1).join(' ') || '',
        birthDate: patient.dob ? new Date(patient.dob) : new Date(),
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
      const cases = await databaseApiClient.getPatientCases(patientId);
      return cases.map(c => ({
        caseId: c.id,
        patientId: c.patient_id,
        status: c.status,
        caseToken: null,
      }));
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

    try {
      const cases = await databaseApiClient.getCases();
      return cases.map(c => ({
        caseId: c.id,
        patientId: c.patient_id,
        status: c.status,
        caseToken: null, // Cases list doesn't include tokens
      }));
    } catch (error) {
      console.error('Error fetching cases from API:', error);
      throw new Error('Failed to fetch cases');
    }
  }

  async getCase(caseId: string) {
    if (config.useMockData) {
      return mockData.findCase(caseId);
    }

    try {
      const caseData = await databaseApiClient.getCase(caseId);
      return {
        caseId: caseData.id,
        patientId: caseData.patient_id,
        status: caseData.status,
        caseToken: null, // Individual case fetch doesn't include token
      };
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
      
      if (searchResult.length > 0) {
        // Patient found - use the first match
        const dbPatient = searchResult[0];
        patient = {
          patientId: dbPatient.id,
          firstName: dbPatient.name.split(' ')[0] || '',
          lastName: dbPatient.name.split(' ').slice(1).join(' ') || '',
          birthDate: dbPatient.dob ? new Date(dbPatient.dob) : new Date(),
        };
      } else {
        // 3. Create patient if not found
        const newPatient = await databaseApiClient.createPatient({
          charite_id: chariteCase.uuid, // Using UUID as charite_id
          name: `${chariteCase.firstName} ${chariteCase.lastName}`,
          sex: chariteCase.sex ?? 'other',
          dob: chariteCase.birthDate.toISOString().split('T')[0], // Convert to ISO date string
          weight: chariteCase.weight,
        });
        patient = {
          patientId: newPatient.id,
          firstName: newPatient.name.split(' ')[0] || '',
          lastName: newPatient.name.split(' ').slice(1).join(' ') || '',
          birthDate: newPatient.dob ? new Date(newPatient.dob) : new Date(),
        };
      }

      // 4. Check if case already exists with this cCaseId
      const patientCases = await databaseApiClient.getPatientCases(patient.patientId);
      const existingCase = patientCases.find((c) => {
        return c.status === 'ONGOING';
      });

      if (existingCase) {
        // Generate a new token for the existing case
        const caseToken = tokenService.generateCaseToken(
          existingCase.id,
          existingCase.patient_id
        );
        
        return {
          created: false,
          caseRecord: {
            caseId: existingCase.id,
            patientId: existingCase.patient_id,
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
        status: 'PLANNED',
        patient_id: patient.patientId,
        devices: [],
        wearables: [],
        contexts: [],
      });

      // Generate secure case token
      const caseToken = tokenService.generateCaseToken(
        newCase.id,
        newCase.patient_id
      );

      return {
        created: true,
        caseRecord: {
          caseId: newCase.id,
          patientId: newCase.patient_id,
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
      const dbPatient = await databaseApiClient.getPatient(caseRecord.patient_id);
      if (!dbPatient) {
        return undefined;
      }

      // Build patient verifier using same logic as mock
      const patientVerifier = mockData.buildPatientVerifier({
        patientId: dbPatient.id,
        firstName: dbPatient.name.split(' ')[0] || '',
        lastName: dbPatient.name.split(' ').slice(1).join(' ') || '',
        birthDate: dbPatient.dob ? new Date(dbPatient.dob) : new Date(),
      });

      return {
        caseRecord: {
          caseId: caseRecord.id,
          patientId: caseRecord.patient_id,
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