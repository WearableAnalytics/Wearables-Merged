import config from '../config.js';
import { databaseApiClient } from '../clients/databaseApi.js';
import * as mockData from '../mockData.js';
import type { CaseStatusEnum, Patient } from '../api/openapi-client/models/index.js';
import { tokenService } from './tokenService.js';
import { logger } from '../logger.js';

export interface CaseCreationResult {
  created: boolean;
  caseRecord: {
    caseId: string;
    patientId: string;
    hospitalCaseId?: string;
    status: CaseStatusEnum;
    caseToken?: string | null;
  };
  patient: Patient | null;
  hospitalCase?: {
    hospitalCaseId: string;
    firstName: string;
    lastName: string;
    birthDate: Date;
  };
}

const activeCaseStatuses = new Set([
  'active',
  'ongoing',
  'planned',
  'in_progress',
  'in-progress',
  'open',
  'pending',
]);

const inactiveCaseStatuses = new Set([
  'inactive',
  'closed',
  'completed',
  'done',
  'cancelled',
  'canceled',
  'archived',
  'resolved',
]);

const normalizeCaseStatus = (status?: string): CaseStatusEnum => {
  const normalizedStatus = (status ?? '').trim().toLowerCase();

  if (activeCaseStatuses.has(normalizedStatus)) {
    return 'active';
  }

  if (inactiveCaseStatuses.has(normalizedStatus)) {
    return 'inactive';
  }

  if (normalizedStatus.includes('active')) {
    return normalizedStatus.startsWith('in') ? 'inactive' : 'active';
  }

  logger.warn('Unknown case status from database, defaulting to inactive', {
    status,
  });
  return 'inactive';
};

const isActiveCaseStatus = (status?: string): boolean =>
  normalizeCaseStatus(status) === 'active';

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
      logger.error('Error fetching patients from API', error as Error);
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
      logger.error(`Error fetching patient ${patientId}`, error as Error);
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
        status: normalizeCaseStatus(c.status),
        caseToken: null,
      }));
    } catch (error) {
      logger.error(`Error fetching cases for patient ${patientId}`, error as Error);
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
        status: normalizeCaseStatus(c.status),
        caseToken: null,
      }));
    } catch (error) {
      logger.error('Error fetching cases from API', error as Error);
      throw new Error('Failed to fetch cases');
    }
  }

  async getCase(caseId: string) {
    if (config.useMockData) {
      return mockData.findCase(caseId);
    }

    try {
      const caseData = await databaseApiClient.getCase(caseId);
      const caseToken = tokenService.generateCaseToken(
        caseData.id,
        caseData.patient_id,
      );
      return {
        caseId: caseData.id,
        patientId: caseData.patient_id,
        status: normalizeCaseStatus(caseData.status),
        caseToken,
      };
    } catch (error) {
      logger.error(`Error fetching case ${caseId}`, error as Error);
      return undefined;
    }
  }

  async createCaseFromHospital(hospitalCaseId: string): Promise<CaseCreationResult | undefined> {
    if (config.useMockData) {
      return mockData.createCaseFromHospital(hospitalCaseId);
    }

    try {
      const hospitalCase = mockData.findHospitalCase(hospitalCaseId);
      if (!hospitalCase) {
        return undefined;
      }

      const searchResult = await databaseApiClient.getPatients({
        firstname: hospitalCase.firstName,
        lastname: hospitalCase.lastName
      });

      let patient: Patient;
      
      if (searchResult.length > 0) {
        const dbPatient = searchResult[0];
        patient = {
          patientId: dbPatient.id,
          firstName: dbPatient.name.split(' ')[0] || '',
          lastName: dbPatient.name.split(' ').slice(1).join(' ') || '',
          birthDate: dbPatient.dob ? new Date(dbPatient.dob) : new Date(),
        };
      } else {
        const newPatient = await databaseApiClient.createPatient({
            charite_id: hospitalCase.uuid,
          name: `${hospitalCase.firstName} ${hospitalCase.lastName}`,
          sex: 'other',
          dob: hospitalCase.birthDate.toISOString().split('T')[0],
        });
        patient = {
          patientId: newPatient.id,
          firstName: newPatient.name.split(' ')[0] || '',
          lastName: newPatient.name.split(' ').slice(1).join(' ') || '',
          birthDate: newPatient.dob ? new Date(newPatient.dob) : new Date(),
        };
      }

      const patientCases = await databaseApiClient.getPatientCases(patient.patientId);
      const existingCase = patientCases.find((c) => isActiveCaseStatus(c.status));

      if (existingCase) {
        const caseToken = tokenService.generateCaseToken(
          existingCase.id,
          existingCase.patient_id
        );
        
        return {
          created: false,
          caseRecord: {
            caseId: existingCase.id,
            patientId: existingCase.patient_id,
            hospitalCaseId,
            status: normalizeCaseStatus(existingCase.status),
            caseToken,
          },
          patient,
          hospitalCase,
        };
      }

      const newCase = await databaseApiClient.createCase({
        status: 'PLANNED',
        patient_id: patient.patientId,
      });

      const caseToken = tokenService.generateCaseToken(
        newCase.id,
        newCase.patient_id
      );

      return {
        created: true,
        caseRecord: {
          caseId: newCase.id,
          patientId: newCase.patient_id,
          hospitalCaseId,
          status: normalizeCaseStatus(newCase.status),
          caseToken,
        },
        patient,
        hospitalCase,
      };
    } catch (error) {
      logger.error('Error creating case from Hospital', error as Error);
      throw error;
    }
  }

  async verifyCaseToken(caseToken: string) {
    if (config.useMockData) {
      return mockData.verifyCaseToken(caseToken);
    }

    try {
      const tokenPayload = tokenService.verifyCaseToken(caseToken);
      if (!tokenPayload) {
        return undefined;
      }
      
      const caseRecord = await databaseApiClient.getCase(tokenPayload.caseId);
      if (!caseRecord) {
        return undefined;
      }

      const dbPatient = await databaseApiClient.getPatient(caseRecord.patient_id);
      if (!dbPatient) {
        return undefined;
      }

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
          status: normalizeCaseStatus(caseRecord.status),
          caseToken,
        },
        patientVerifier,
      };
    } catch (error) {
      logger.error('Error verifying case token', error as Error);
      return undefined;
    }
  }
}

class HospitalCaseService {
  async findHospitalCase(hospitalCaseId: string) {
    return mockData.findHospitalCase(hospitalCaseId);
  }
}

export const patientService = new PatientService();
export const caseService = new CaseService();
export const hospitalCaseService = new HospitalCaseService();
