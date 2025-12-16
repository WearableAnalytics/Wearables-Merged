import cors from 'cors';
import express, { Request, Response } from 'express';
import {
  casesForPatient,
  createCaseFromCharite,
  findCase,
  findChariteCase,
  findPatient,
  listCases,
  listPatients,
  verifyCaseToken,
} from './mockData';
import type {
  CasesFromChariteCasePostRequest,
  CasesVerifyTokenPostRequest,
} from './api/openapi-client/models';

const app = express();
const port = Number(process.env.PORT) || 3001;
const apiPrefix = (process.env.API_PREFIX ?? '/api').replace(/\/$/, '');
// Allow local dev (5173) and dockerized frontend (8080) by default; override via FRONTEND_URL.
const frontendOrigins = (process.env.FRONTEND_URL ?? 'http://localhost:5173,http://localhost:8080')
  .split(',')
  .map((url) => url.trim())
  .filter(Boolean);

app.use(cors({ origin: frontendOrigins, credentials: true }));
app.use(express.json());

const route = (path: string) => `${apiPrefix}${path}`;

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

app.get(route('/charite/cases/:cCaseId'), (req, res) => {
  const chariteCase = findChariteCase(req.params.cCaseId);
  if (!chariteCase) {
    return sendError(res, 404, 'Charité case not found', 'NOT_FOUND');
  }

  return res.json(chariteCase);
});

app.get(route('/patients'), (_req, res) => {
  return res.json(listPatients());
});

app.get(route('/patients/:patientId'), (req, res) => {
  const patient = findPatient(req.params.patientId);
  if (!patient) {
    return sendError(res, 404, 'Patient not found', 'NOT_FOUND');
  }

  return res.json(patient);
});

app.get(route('/patients/:patientId/cases'), (req, res) => {
  const patient = findPatient(req.params.patientId);
  if (!patient) {
    return sendError(res, 404, 'Patient not found', 'NOT_FOUND');
  }

  return res.json(casesForPatient(req.params.patientId));
});

app.get(route('/cases'), (_req, res) => {
  return res.json(listCases());
});

app.get(route('/cases/:caseId'), (req, res) => {
  const caseRecord = findCase(req.params.caseId);
  if (!caseRecord) {
    return sendError(res, 404, 'Case not found', 'NOT_FOUND');
  }

  return res.json(caseRecord);
});

app.post(route('/cases/from-charite-case'), (req: Request, res: Response) => {
  const { cCaseId } = (req.body ?? {}) as CasesFromChariteCaseBody;
  if (typeof cCaseId !== 'string' || !cCaseId) {
    return sendError(res, 400, 'cCaseId is required');
  }

  const creationResult = createCaseFromCharite(cCaseId);
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
});

app.post(route('/cases/verify-token'), (req: Request, res: Response) => {
  const { caseToken } = (req.body ?? {}) as CasesVerifyTokenBody;
  if (typeof caseToken !== 'string' || !caseToken) {
    return sendError(res, 400, 'caseToken is required');
  }

  const verification = verifyCaseToken(caseToken);
  if (!verification) {
    return sendError(res, 401, 'Invalid or expired token', 'INVALID_TOKEN');
  }

  const { caseRecord, patientVerifier } = verification;
  return res.json({
    caseId: caseRecord.caseId,
    patientVerifier,
    status: caseRecord.status,
  });
});

app.use((_req, res) => {
  return sendError(res, 404, 'Route not found', 'NOT_FOUND');
});

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Mock registration service listening on http://localhost:${port}${apiPrefix}`);
});
