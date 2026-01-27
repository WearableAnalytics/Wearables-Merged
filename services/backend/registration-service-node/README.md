# Mock Registration Service (Node.js)

Lightweight Express server that implements the API described in `packages/api-schema` with mocked data. Use it to develop the web app without spinning up the full backend stack.

## Run locally

```bash
cd services/backend/registration-service-node
npm install
npm run dev
```

Environment variables:

- `PORT` (default `3001`)
- `API_PREFIX` (default `/api`) – set to `` when pointing `VITE_API_BASE_URL` directly at the server root.

When running the web frontend, set `VITE_API_BASE_URL=http://localhost:3001` (or match whatever host/port you used).

## Keep API typings in sync

This mock server uses the same OpenAPI source as the frontend and keeps the same `defaultApi` + `openapi-client` structure. Regenerate local client/types after schema changes:

```bash
npm run generate:api
```

That command rebuilds `packages/api-schema/openapi.json` and then regenerates the client in `src/api/openapi-client` (plus updates any shared types referenced by the mock server).

## Mocked endpoints

- `GET    {API_PREFIX}/health`
- `GET    {API_PREFIX}/charite/cases/:cCaseId`
- `GET    {API_PREFIX}/patients`
- `GET    {API_PREFIX}/patients/:patientId`
- `GET    {API_PREFIX}/patients/:patientId/cases`
- `GET    {API_PREFIX}/cases`
- `GET    {API_PREFIX}/cases/:caseId`
- `POST   {API_PREFIX}/cases/from-charite-case`
- `POST   {API_PREFIX}/cases/verify-token`

Responses follow the shapes from `packages/api-schema` and return predictable mock objects without persisting to a database.
