import jwt from 'jsonwebtoken';
import { logger } from '../logger.js';
import config from '../config.js';

interface CaseTokenPayload {
  caseId: string;
  patientId: string;
  type: 'case-verification';
}

interface StoredToken {
  caseId: string;
  patientId: string;
  createdAt: Date;
  expiresAt: Date;
}

class TokenService {
  private tokenStore = new Map<string, StoredToken>();

  private getSecret(): string {
    return config.jwtSecret;
  }

  generateCaseToken(caseId: string, patientId: string): string {
    const expiry = config.caseTokenExpirySeconds;
    const expiresAt = new Date(Date.now() + expiry * 1000);

    const payload: CaseTokenPayload = {
      caseId,
      patientId,
      type: 'case-verification',
    };

    const token = jwt.sign(payload, this.getSecret(), {
      expiresIn: Math.floor(expiry),
      issuer: config.tokenIssuer,
      subject: caseId,
    });

    this.tokenStore.set(token, {
      caseId,
      patientId,
      createdAt: new Date(),
      expiresAt,
    });

    this.cleanupExpiredTokens();
    return token;
  }

  verifyCaseToken(token: string): CaseTokenPayload | null {
    try {
      const decoded = jwt.verify(token, this.getSecret(), {
        issuer: config.tokenIssuer,
      }) as CaseTokenPayload;

      if (decoded.type !== 'case-verification') {
        logger.warn('Invalid token type', { tokenType: decoded.type });
        return null;
      }

      const stored = this.tokenStore.get(token);
      if (!stored) {
        logger.warn('Token not found in store, allowing based on JWT verification');
        return decoded;
      }

      if (stored.expiresAt < new Date()) {
        this.tokenStore.delete(token);
        return null;
      }

      return decoded;
    } catch (error) {
      if (error instanceof jwt.JsonWebTokenError) {
        logger.warn('Invalid token', { message: error.message });
      } else if (error instanceof jwt.TokenExpiredError) {
        logger.warn('Token expired', { message: error.message });
        this.tokenStore.delete(token);
      } else {
        logger.error('Token verification error', error as Error);
      }
      return null;
    }
  }

  revokeToken(token: string): boolean {
    return this.tokenStore.delete(token);
  }

  revokeAllTokensForCase(caseId: string): number {
    let count = 0;
    for (const [token, data] of this.tokenStore.entries()) {
      if (data.caseId === caseId) {
        this.tokenStore.delete(token);
        count++;
      }
    }
    return count;
  }

  private cleanupExpiredTokens(): void {
    const now = new Date();
    for (const [token, data] of this.tokenStore.entries()) {
      if (data.expiresAt < now) {
        this.tokenStore.delete(token);
      }
    }
  }

  getTokenInfo(token: string): StoredToken | undefined {
    return this.tokenStore.get(token);
  }
}

export const tokenService = new TokenService();
