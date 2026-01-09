import crypto from 'crypto';
import jwt from 'jsonwebtoken';

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
  // (replace with database in production)
  private tokenStore = new Map<string, StoredToken>();
  
  // Default expiration: 8 days for case tokens
  private readonly DEFAULT_EXPIRY_S = 8 * 24 * 60 * 60;
  
  private getSecret(): string {
    return process.env.JWT_SECRET!;
  }

  /**
   * Generate a secure case token using JWT
   */
  generateCaseToken(caseId: string, patientId: string): string {
    const expiry = this.DEFAULT_EXPIRY_S;
    const expiresAt = new Date(Date.now() + expiry * 1000);
    
    const payload: CaseTokenPayload = {
      caseId,
      patientId,
      type: 'case-verification',
    };

    // Generate JWT token
    const token = jwt.sign(payload, this.getSecret(), {
      expiresIn: Math.floor(expiry),
      issuer: 'registration-service',
      subject: caseId,
    });

    // Store token metadata for additional validation
    this.tokenStore.set(token, {
      caseId,
      patientId,
      createdAt: new Date(),
      expiresAt,
    });

    this.cleanupExpiredTokens();
    return token;
  }

  /**
   * Verify and decode a case token
   */
  verifyCaseToken(token: string): CaseTokenPayload | null {
    try {
      // JWT signature and expiration
      const decoded = jwt.verify(token, this.getSecret(), {
        issuer: 'registration-service',
      }) as CaseTokenPayload;

      // Check if token type is correct
      if (decoded.type !== 'case-verification') {
        console.warn('Invalid token type:', decoded.type);
        return null;
      }

      // Check token store for additional validation
      const stored = this.tokenStore.get(token);
      if (!stored) {
        // Token not in store - could be old or from before restart
        // In production, this should query a persistent store
        console.warn('Token not found in store, allowing based on JWT verification');
        return decoded;
      }

      // Check expiration in store
      if (stored.expiresAt < new Date()) {
        this.tokenStore.delete(token);
        return null;
      }

      return decoded;
    } catch (error) {
      if (error instanceof jwt.JsonWebTokenError) {
        console.warn('Invalid token:', error.message);
      } else if (error instanceof jwt.TokenExpiredError) {
        console.warn('Token expired:', error.message);
        this.tokenStore.delete(token);
      } else {
        console.error('Token verification error:', error);
      }
      return null;
    }
  }

  /**
   * Revoke a token
   */
  revokeToken(token: string): boolean {
    return this.tokenStore.delete(token);
  }

  /**
   * Revoke all tokens for a specific case
   */
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

  /**
   * Clean up expired tokens from the store
   */
  private cleanupExpiredTokens(): void {
    const now = new Date();
    for (const [token, data] of this.tokenStore.entries()) {
      if (data.expiresAt < now) {
        this.tokenStore.delete(token);
      }
    }
  }

  /**
   * Get token info
   */
  getTokenInfo(token: string): StoredToken | undefined {
    return this.tokenStore.get(token);
  }
}

export const tokenService = new TokenService();
