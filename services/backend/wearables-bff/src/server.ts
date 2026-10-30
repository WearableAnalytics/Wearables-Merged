import cors from 'cors';
import express from 'express';
import config from './config.js';
import authRouter from './api/routes/auth.js';
import extractionRouter from './api/routes/extraction.js';
import apiTokensRouter from './api/routes/apiTokens.js';
import {
  auth,
  requestLogger,
  requireCommandOrigin,
  admitHttpRequest,
  errorHandler,
} from './middleware.js';
import { asyncRoute, controlRequest, ControlApiError } from './clients/controlApi.js';
import { clinicalCase, clinicalCases, type ClinicalMetadata } from './clients/clinicalMetadata.js';
import { actor, actorQuery, isUuid } from './clients/caseAccess.js';
import { getUserByEmail, initializeUsers } from './services/userStore.js';
import { logger } from './logger.js';

export const app = express();
const route = (path: string) => `${config.apiPrefix}${path}`;
app.disable('x-powered-by');
app.use(cors({ origin: config.frontendOrigins, credentials: true }));
app.use(admitHttpRequest);
app.use(express.json({ limit: '32kb' }));
app.use(requestLogger);
app.use(config.apiPrefix, (_req, res, next) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  next();
});
app.use(config.apiPrefix, requireCommandOrigin);
app.use(config.apiPrefix, authRouter);
app.get(route('/health'), (_req, res) => res.json({ status: 'ok' }));
// No broad export passthrough can bypass a case assignment.
app.use(route('/extraction'), extractionRouter);
app.use(config.apiPrefix, auth.required);
app.use(config.apiPrefix, apiTokensRouter);

app.get(
  route('/admin/staff-lookup'),
  ...auth.adminOnly,
  asyncRoute(async (req, res) => {
    if (typeof req.query.email !== 'string' || req.query.email.length > 320)
      throw new ControlApiError(422);
    const user = await getUserByEmail(req.query.email);
    res.json({
      user:
        user?.status === 'approved'
          ? {
              id: user.id,
              email: user.email,
              isAdmin: user.isAdmin,
              roles: user.roles,
            }
          : null,
    });
  }),
);
app.get(
  route('/admin/case-access/:caseId/:userId'),
  ...auth.adminOnly,
  asyncRoute(async (req, res) => {
    if (!isUuid(req.params.caseId) || !isUuid(req.params.userId)) throw new ControlApiError(422);
    res.json(
      await controlRequest(
        `/case-access/${req.params.caseId}/${req.params.userId}?${actorQuery(req.user!)}`,
      ),
    );
  }),
);
app.put(
  route('/admin/case-access/:caseId/:userId'),
  ...auth.adminOnly,
  asyncRoute(async (req, res) => {
    if (!isUuid(req.params.caseId) || !isUuid(req.params.userId)) throw new ControlApiError(422);
    // Never accept actor identity from the browser. The DB also checks this session version.
    const { expected_revision, active, purpose, scopes, reason, ...unknown } = req.body ?? {};
    if (Object.keys(unknown).length) throw new ControlApiError(422);
    res.json(
      await controlRequest(`/case-access/${req.params.caseId}/${req.params.userId}`, 'PUT', {
        ...actor(req.user!),
        expected_revision,
        active,
        purpose,
        scopes,
        reason,
      }),
    );
  }),
);

app.use(config.apiPrefix, auth.practitionerOrAdmin);
const asCase = (row: ClinicalMetadata) => ({
  caseId: row.id,
  patientId: row.patient_id,
  status: ['PLANNED', 'ONGOING'].includes(row.status) ? 'active' : 'inactive',
  caseToken: null,
});
const asPatient = (row: ClinicalMetadata) => ({
  patientId: row.patient.id,
  firstName: row.patient.name.split(' ')[0] || '',
  lastName: row.patient.name.split(' ').slice(1).join(' ') || '',
  birthDate: row.patient.dob,
});
app.get(
  route('/patients'),
  asyncRoute(async (req, res) => {
    const rows = await clinicalCases(req.user!);
    res.json([...new Map(rows.map((row) => [row.patient_id, asPatient(row)])).values()]);
  }),
);
app.get(
  route('/patients/:patientId'),
  asyncRoute(async (req, res) => {
    const rows = await clinicalCases(req.user!, req.params.patientId, true);
    if (!rows.length) throw new ControlApiError(403, 'CASE_ACCESS_REQUIRED');
    res.json(asPatient(rows[0]));
  }),
);
app.get(
  route('/patients/:patientId/cases'),
  asyncRoute(async (req, res) => {
    res.json((await clinicalCases(req.user!, req.params.patientId)).map(asCase));
  }),
);
app.get(
  route('/cases'),
  asyncRoute(async (req, res) => {
    res.json((await clinicalCases(req.user!)).map(asCase));
  }),
);
app.get(
  route('/cases/:caseId'),
  asyncRoute(async (req, res) => {
    res.json(asCase(await clinicalCase(req.user!, req.params.caseId)));
  }),
);
// These old endpoints used a sample hospital lookup and long-lived mobile tokens.
// Keep those workflows separate from staff permission management.
app.get(route('/hospital/cases/:hospitalCaseId'), (_req, res) => {
  res
    .status(503)
    .json({
      code: 'HOSPITAL_IDENTITY_REQUIRED',
      message: 'Verified hospital case lookup is not configured.',
    });
});
app.post(route('/cases/from-hospital-case'), (_req, res) => {
  res
    .status(503)
    .json({
      code: 'HOSPITAL_IDENTITY_REQUIRED',
      message: 'Use the operator case import and an explicit staff assignment.',
    });
});
app.post(route('/cases/verify-token'), (_req, res) => {
  res
    .status(410)
    .json({
      code: 'MOBILE_ENROLLMENT_REQUIRED',
      message: 'Mobile enrollment is a separate feature.',
    });
});
app.use((_req, res) => res.status(404).json({ message: 'Route not found' }));
app.use(errorHandler);

// Startup fails if durable account authority cannot be reached. Never use memory as fallback.
if (process.env.BFF_TEST_MODE !== 'true') {
  await initializeUsers();
  app.listen(config.port, config.devAuthBypass ? '127.0.0.1' : '0.0.0.0', () =>
    logger.info('bff.started', { port: config.port }),
  );
}
