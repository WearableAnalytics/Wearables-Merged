import cors from 'cors';
import express, { Request, Response } from 'express';
import config from './config.js';
import authRouter from './api/routes/auth.js';
import { auth } from './middleware.js';
import { patientService, caseService, chariteCaseService } from './services/index.js';
import type {
  CasesFromChariteCasePostRequest,
  CasesVerifyTokenPostRequest,
} from './api/openapi-client/models';

const app = express();

app.use(cors({ origin: config.frontendOrigins, credentials: true }));
app.use(express.json());
app.use(config.apiPrefix, authRouter);

const route = (path: string) => `${config.apiPrefix}${path}`;

function sendError(res: Response, status: number, message: string, code?: string) {
  return res.status(status).json({ message, code });
}

type CasesFromChariteCaseBody =
  CasesFromChariteCasePostRequest;
type CasesVerifyTokenBody =
  CasesVerifyTokenPostRequest;

app.get(route('/health'), (_req, res) => {
  res.json({ status: 'ok' });
});

app.use(config.apiPrefix, auth.required);

app.get(route('/charite/cases/:cCaseId'), async (req, res) => {
  try {
    const chariteCase = await chariteCaseService.findChariteCase(req.params.cCaseId);
    if (!chariteCase) {
      return sendError(res, 404, 'Charité case not found', 'NOT_FOUND');
    }

    return res.json(chariteCase);
  } catch (error) {
    console.error('Error fetching Charité case:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.get(route('/patients'), async (_req, res) => {
  try {
    const patients = await patientService.listPatients();
    return res.json(patients);
  } catch (error) {
    console.error('Error listing patients:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.get(route('/patients/:patientId'), async (req, res) => {
  try {
    const patient = await patientService.getPatient(req.params.patientId);
    if (!patient) {
      return sendError(res, 404, 'Patient not found', 'NOT_FOUND');
    }

    return res.json(patient);
  } catch (error) {
    console.error('Error fetching patient:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.get(route('/patients/:patientId/cases'), async (req, res) => {
  try {
    const patient = await patientService.getPatient(req.params.patientId);
    if (!patient) {
      return sendError(res, 404, 'Patient not found', 'NOT_FOUND');
    }

    const cases = await patientService.getPatientCases(req.params.patientId);
    return res.json(cases);
  } catch (error) {
    console.error('Error fetching patient cases:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.get(route('/cases'), async (_req, res) => {
  try {
    const cases = await caseService.listCases();
    return res.json(cases);
  } catch (error) {
    console.error('Error listing cases:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.get(route('/cases/:caseId'), async (req, res) => {
  try {
    const caseRecord = await caseService.getCase(req.params.caseId);
    if (!caseRecord) {
      return sendError(res, 404, 'Case not found', 'NOT_FOUND');
    }

    return res.json(caseRecord);
  } catch (error) {
    console.error('Error fetching case:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.post(route('/cases/from-charite-case'), async (req: Request, res: Response) => {
  const { cCaseId } = (req.body ?? {}) as CasesFromChariteCaseBody;
  if (typeof cCaseId !== 'string' || !cCaseId) {
    return sendError(res, 400, 'cCaseId is required');
  }

  try {
    const creationResult = await caseService.createCaseFromCharite(cCaseId);
    if (!creationResult) {
      return sendError(res, 404, 'Charité case not found', 'NOT_FOUND');
    }

    const { created, caseRecord } = creationResult;
    const payload = {
      patientId: caseRecord.patientId,
      caseId: caseRecord.caseId,
      caseToken: caseRecord.caseToken ?? 'case-token-not-set',
    };

    return res.status(created ? 201 : 200).json(payload);
  } catch (error) {
    console.error('Error creating case from Charité:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.post(route('/cases/verify-token'), async (req: Request, res: Response) => {
  const { caseToken } = (req.body ?? {}) as CasesVerifyTokenBody;
  if (typeof caseToken !== 'string' || !caseToken) {
    return sendError(res, 400, 'caseToken is required');
  }

  try {
    const verification = await caseService.verifyCaseToken(caseToken);
    if (!verification) {
      return sendError(res, 401, 'Invalid or expired token', 'INVALID_TOKEN');
    }

    const { caseRecord, patientVerifier } = verification;
    return res.json({
      caseId: caseRecord.caseId,
      patientVerifier,
      status: caseRecord.status,
    });
  } catch (error) {
    console.error('Error verifying case token:', error);
    return sendError(res, 500, 'Internal server error');
  }
});

app.use((_req, res) => {
  return sendError(res, 404, 'Route not found', 'NOT_FOUND');
});

app.listen(config.port, () => {
  // eslint-disable-next-line no-console
  console.log(`Registration service listening on http://localhost:${config.port}${config.apiPrefix}`);
  console.log(`Using ${config.useMockData ? 'MOCK' : 'REAL'} data`);
  if (!config.useMockData) {
    console.log(`Database API URL: ${config.databaseApi.baseUrl}`);
  }
});
