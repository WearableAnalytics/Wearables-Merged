import config from '../config.js';
import type { NextFunction, Request, RequestHandler, Response } from 'express';

export class ControlApiError extends Error {
  constructor(
    readonly status: number,
    readonly code = status === 503 ? 'POLICY_UNAVAILABLE' : 'CONTROL_REJECTED',
  ) {
    super(
      code === 'CONTROL_LIST_LIMIT'
        ? 'User list exceeds the configured page budget'
        : status === 503
          ? 'Current policy is unavailable'
          : 'Control operation rejected',
    );
    this.name = 'ControlApiError';
  }
}

let activeRequests = 0;
export const controlRequest = async <T>(
  path: string,
  method = 'GET',
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> => {
  if (activeRequests >= config.controlMaxInflightRequests)
    throw new ControlApiError(503, 'CONTROL_CAPACITY');
  activeRequests++;
  const abort = new AbortController();
  const cancel = () => abort.abort();
  if (signal?.aborted) cancel();
  else signal?.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => abort.abort(), config.controlTimeoutSeconds * 1000);
  try {
    const response = await fetch(`${config.databaseApi.baseUrl}/control${path}`, {
      method,
      signal: abort.signal,
      redirect: 'error',
      headers: {
        'Content-Type': 'application/json',
        'X-Control-Service-Token': config.controlWriteToken,
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) {
      // Never include upstream response bodies or credentials in errors/logs.
      await response.body?.cancel();
      throw new ControlApiError(
        [400, 403, 404, 409, 422].includes(response.status) ? response.status : 503,
      );
    }
    // Control records are small. Keep malformed responses from using unbounded memory.
    const reader = response.body?.getReader();
    if (!reader) throw new ControlApiError(503);
    const chunks: Uint8Array[] = [];
    let bytes = 0;
    while (true) {
      const result = await reader.read();
      if (result.done) break;
      bytes += result.value.byteLength;
      if (bytes > 1_048_576) {
        await reader.cancel();
        throw new ControlApiError(503, 'CONTROL_RESPONSE_LIMIT');
      }
      chunks.push(result.value);
    }
    return JSON.parse(Buffer.concat(chunks).toString('utf8')) as T;
  } catch (error) {
    if (error instanceof ControlApiError) throw error;
    throw new ControlApiError(503);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
    activeRequests--;
  }
};

export const sendControlError = (res: Response, error: unknown): boolean => {
  if (!(error instanceof ControlApiError)) return false;
  res.status(error.status).json({ error: error.message, code: error.code });
  return true;
};

/** Express 4 does not forward rejected async handlers itself. */
export const asyncRoute =
  (handler: (req: Request, res: Response, next: NextFunction) => unknown): RequestHandler =>
  (req, res, next) => {
    Promise.resolve()
      .then(() => handler(req, res, next))
      .catch((error) => {
        if (!sendControlError(res, error)) res.status(500).json({ error: 'Request failed' });
      });
  };
