import { z } from 'zod';
import {
  extendZodWithOpenApi,
  OpenAPIRegistry,
  OpenApiGeneratorV3,
} from '@asteasolutions/zod-to-openapi';

extendZodWithOpenApi(z);

export const registry = new OpenAPIRegistry();

// Components
export const HospitalCaseSchema = registry.register(
  'HospitalCase',
  z
    .object({
      hospitalCaseId: z.string().describe('Hospital case identifier').openapi({ example: 'C-123456' }),
      firstName: z.string().describe('Patient first name').openapi({ example: 'Max' }),
      lastName: z.string().describe('Patient last name').openapi({ example: 'Mustermann' }),
      birthDate: z
        .string()
        .describe('Patient date of birth')
        .openapi({ format: 'date', example: '1980-01-01' }),
    })
    .describe('External read-only Hospital case')
    .strict(),
);

export const PatientSchema = registry.register(
  'Patient',
  z
    .object({
      patientId: z.string().describe('Internal patient identifier').openapi({ example: 'P-98765' }),
      firstName: z.string().describe('Patient first name').openapi({ example: 'Max' }),
      lastName: z.string().describe('Patient last name').openapi({ example: 'Mustermann' }),
      birthDate: z
        .string()
        .describe('Patient date of birth')
        .openapi({ format: 'date', example: '1980-01-01' }),
    })
    .describe('Internal patient')
    .strict(),
);

const caseStatusSchema = z.enum(['active', 'inactive']).describe('Case status').openapi({
  example: 'active',
});

export const CaseSchema = registry.register(
  'Case',
  z
    .object({
      caseId: z.string().describe('Internal case identifier').openapi({ example: 'IC-54321' }),
      patientId: z.string().describe('Associated patient identifier').openapi({ example: 'P-98765' }),
      hospitalCaseId: z
        .string()
        .describe('Original Hospital case identifier')
        .openapi({ example: 'C-123456' })
        .optional(),
      status: caseStatusSchema,
      caseToken: z
        .string()
        .nullable()
        .describe('JWT token for case access')
        .openapi({ example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' })
        .optional(),
    })
    .describe('Internal case')
    .strict(),
);

export const CaseCreatedSchema = registry.register(
  'CaseCreated',
  z
    .object({
      patientId: z.string().describe('Internal patient identifier').openapi({ example: 'P-98765' }),
      caseId: z.string().describe('Internal case identifier').openapi({ example: 'IC-54321' }),
      caseToken: z
        .string()
        .describe('JWT token for case access')
        .openapi({ example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...' }),
    })
    .describe('Response after case creation')
    .strict(),
);

export const CaseVerifiedSchema = registry.register(
  'CaseVerified',
  z
    .object({
      caseId: z.string().describe('Internal case identifier').openapi({ example: 'IC-54321' }),
      patientVerifier: z
        .string()
        .describe(
          'Patient verification string built from first letter of first name, birthdate (DDMM), and first letter of last name.',
        )
        .openapi({ example: 'M0212B' }),
      status: caseStatusSchema,
    })
    .describe('Response after token verification')
    .strict(),
);

export const ApiTokenSchema = registry.register(
  'ApiToken',
  z
    .object({
      id: z.string().uuid(),
      name: z.string().describe('Name given by the owner, e.g. the computer it is used on'),
      token_hint: z.string().describe('Last characters of the token'),
      owner_email: z.string(),
      created_at: z.string().datetime({ offset: true }),
      last_used_at: z.string().datetime({ offset: true }).nullable(),
      revoked_at: z.string().datetime({ offset: true }).nullable(),
      revoked_by: z.string().nullable(),
    })
    .describe('Personal export API token (without the token itself)')
    .strict(),
);

export const CreatedApiTokenSchema = registry.register(
  'CreatedApiToken',
  ApiTokenSchema.extend({
    token: z
      .string()
      .describe('The token. Returned only once; only its sha256 hash is stored.')
      .openapi({ example: 'wrt_3q2-example' }),
  })
    .describe('Newly created API token')
    .strict(),
);

export const ErrorSchema = registry.register(
  'Error',
  z
    .object({
      message: z.string().describe('Error message').openapi({ example: 'Resource not found' }),
      code: z.string().describe('Error code').openapi({ example: 'NOT_FOUND' }).optional(),
    })
    .describe('Error response')
    .strict(),
);

// Request bodies
const CreateCaseFromHospitalBodySchema = z
  .object({
    hospitalCaseId: z
      .string()
      .describe('Hospital case identifier')
      .openapi({ example: 'C-123456' }),
  })
  .describe('Create internal case from Hospital case payload')
  .strict();

const VerifyCaseTokenBodySchema = z
  .object({
    caseToken: z
      .string()
      .describe('JWT case token')
      .openapi({ example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpX...' }),
  })
  .describe('Verify case token payload')
  .strict();

// Paths
registry.registerPath({
  method: 'get',
  path: '/hospital/cases/{hospitalCaseId}',
  tags: ['Hospital Cases'],
  summary: 'Get a Hospital case',
  description: 'Returns a read-only Hospital case by ID',
  request: {
    params: z.object({
      hospitalCaseId: z
        .string()
        .describe('Hospital case identifier')
        .openapi({ example: 'C-123456' }),
    }),
  },
  responses: {
    200: {
      description: 'Hospital case retrieved successfully',
      content: { 'application/json': { schema: HospitalCaseSchema } },
    },
    404: {
      description: 'Hospital case not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/patients',
  tags: ['Patients'],
  summary: 'List internal patients',
  description: 'Returns a list of all internal patients',
  responses: {
    200: {
      description: 'List of patients retrieved successfully',
      content: { 'application/json': { schema: z.array(PatientSchema) } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/patients/{patientId}',
  tags: ['Patients'],
  summary: 'Get a single patient',
  description: 'Returns a single internal patient by ID',
  request: {
    params: z.object({
      patientId: z
        .string()
        .describe('Internal patient identifier')
        .openapi({ example: 'P-98765' }),
    }),
  },
  responses: {
    200: {
      description: 'Patient retrieved successfully',
      content: { 'application/json': { schema: PatientSchema } },
    },
    404: {
      description: 'Patient not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/patients/{patientId}/cases',
  tags: ['Patients'],
  summary: 'List cases for a patient',
  description: 'Returns all cases linked to a specific patient',
  request: {
    params: z.object({
      patientId: z
        .string()
        .describe('Internal patient identifier')
        .openapi({ example: 'P-98765' }),
    }),
  },
  responses: {
    200: {
      description: 'List of cases retrieved successfully',
      content: { 'application/json': { schema: z.array(CaseSchema) } },
    },
    404: {
      description: 'Patient not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/cases',
  tags: ['Cases'],
  summary: 'List all internal cases',
  description: 'Returns a list of all internal cases',
  responses: {
    200: {
      description: 'List of cases retrieved successfully',
      content: { 'application/json': { schema: z.array(CaseSchema) } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/cases/{caseId}',
  tags: ['Cases'],
  summary: 'Get a single case',
  description: 'Returns a single internal case by ID',
  request: {
    params: z.object({
      caseId: z
        .string()
        .describe('Internal case identifier')
        .openapi({ example: 'IC-54321' }),
    }),
  },
  responses: {
    200: {
      description: 'Case retrieved successfully',
      content: { 'application/json': { schema: CaseSchema } },
    },
    404: {
      description: 'Case not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'post',
  path: '/cases/from-hospital-case',
  tags: ['Cases'],
  summary: 'Create internal case from Hospital case',
  description:
    'Creates an internal case from an external Hospital case with the specified conflict-resolution rules.',
  request: {
    body: {
      required: true,
      content: {
        'application/json': {
          schema: CreateCaseFromHospitalBodySchema,
        },
      },
    },
  },
  responses: {
    201: {
      description: 'Case created successfully',
      content: { 'application/json': { schema: CaseCreatedSchema } },
    },
    200: {
      description: 'Case already exists',
      content: { 'application/json': { schema: CaseCreatedSchema } },
    },
    400: {
      description: 'Invalid input',
      content: { 'application/json': { schema: ErrorSchema } },
    },
    404: {
      description: 'Hospital case not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'get',
  path: '/researcher/api-tokens',
  tags: ['Researcher'],
  summary: 'List your active API tokens',
  responses: {
    200: {
      description: 'Active tokens of the logged-in user',
      content: { 'application/json': { schema: z.array(ApiTokenSchema) } },
    },
    401: {
      description: 'Authentication required',
      content: { 'application/json': { schema: ErrorSchema } },
    },
    403: {
      description: 'Researcher or admin access required',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'post',
  path: '/researcher/api-tokens',
  tags: ['Researcher'],
  summary: 'Create a personal API token for the export API',
  request: {
    body: {
      content: {
        'application/json': { schema: z.object({ name: z.string().min(1).max(100) }).strict() },
      },
    },
  },
  responses: {
    201: {
      description: 'Token created; the token is only returned in this response',
      content: { 'application/json': { schema: CreatedApiTokenSchema } },
    },
    401: {
      description: 'Authentication required',
      content: { 'application/json': { schema: ErrorSchema } },
    },
    403: {
      description: 'Researcher or admin access required',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'post',
  path: '/researcher/api-tokens/{tokenId}/revoke',
  tags: ['Researcher'],
  summary: 'Revoke one of your API tokens',
  request: { params: z.object({ tokenId: z.string().uuid() }) },
  responses: {
    200: {
      description: 'Token revoked',
      content: { 'application/json': { schema: ApiTokenSchema } },
    },
    401: {
      description: 'Authentication required',
      content: { 'application/json': { schema: ErrorSchema } },
    },
    403: {
      description: 'Researcher or admin access required',
      content: { 'application/json': { schema: ErrorSchema } },
    },
    404: {
      description: 'Token not found',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

registry.registerPath({
  method: 'post',
  path: '/cases/verify-token',
  tags: ['Cases'],
  summary: 'Verify a case token',
  description: 'Verifies a case token and returns the linked case information',
  request: {
    body: {
      required: true,
      content: {
        'application/json': {
          schema: VerifyCaseTokenBodySchema,
        },
      },
    },
  },
  responses: {
    200: {
      description: 'Token verified successfully',
      content: { 'application/json': { schema: CaseVerifiedSchema } },
    },
    401: {
      description: 'Invalid or expired token',
      content: { 'application/json': { schema: ErrorSchema } },
    },
  },
});

export function generateOpenApiDocument() {
  const generator = new OpenApiGeneratorV3(registry.definitions);
  return generator.generateDocument({
    openapi: '3.0.3',
    info: {
      title: 'Patient & Case API',
      version: '1.0.0',
      description: `Endpoints for fetching read-only Hospital cases and managing internal patients/cases.

## Frontend Flow
1. Enter a Hospital case ID (hospitalCaseId)
2. Fetch and display the external Hospital case
3. User clicks "Create Case" to create an internal case
4. Show that patient/case was created and store the caseId
5. Display the case token as QR code for scanning in the Hospital app

## Existing Patient Access
1. Fetch all internal patients/cases
2. User selects a patient/case to view details
3. Display case details and show case token as QR code

## App Flow
1. Receive a caseToken scanned from Hospital app
2. Fetch the internal case using POST /cases/verify-token
3. Display case details
4. Allow user to proceed with further actions`,
      contact: { name: 'API Support' },
    },
    servers: [{ url: 'https://api.example.com/v1', description: 'Production server' }],
    tags: [
      { name: 'Hospital Cases', description: 'Read-only external Hospital cases' },
      { name: 'Patients', description: 'Internal patient management' },
      { name: 'Cases', description: 'Internal case management' },
      { name: 'Researcher', description: 'Researcher-only API access' },
    ],
  });
}
