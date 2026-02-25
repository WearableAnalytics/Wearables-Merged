import config from '../config.js';
import { logger } from '../logger.js';

type Sender = { name: string; email: string };

const shouldLogOnly = !config.isProduction || !config.brevoApiKey;

function getBackendUrl(): string {
  return config.backendUrl;
}

function getFrontendUrl(): string {
  return config.frontendRedirectUrl;
}

function buildMagicLink(token: string, redirect?: string): string {
  const baseUrl = getBackendUrl();
  const params = new URLSearchParams({ token });
  if (redirect) {
    params.set('redirect', redirect);
  }
  return `${baseUrl}${config.apiPrefix}/verify-magiclink?${params.toString()}`;
}

function formatMagicLinkValidity(seconds: number): string {
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return `${hours} hour${hours === 1 ? '' : 's'}`;
  }
  if (seconds % 60 === 0) {
    const minutes = seconds / 60;
    return `${minutes} minute${minutes === 1 ? '' : 's'}`;
  }
  return `${seconds} second${seconds === 1 ? '' : 's'}`;
}

async function sendEmail(
  to: string,
  subject: string,
  htmlContent: string,
) {
  if (shouldLogOnly || to.includes('@example.com')) {
    return;
  }

  const sender: Sender = {
    name: config.mailerFromName!,
    email: config.mailerFromEmail!,
  };

  const response = await fetch('https://api.brevo.com/v3/smtp/email', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      'api-key': config.brevoApiKey ?? '',
    },
    body: JSON.stringify({
      to: [{ email: to }],
      sender,
      subject,
      htmlContent,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Brevo send failed: ${response.status} ${body}`);
  }
}

export async function sendMagicLinkEmail(
  email: string,
  token: string,
  options: { isRegistration?: boolean; redirect?: string } = {},
) {
  const magicLink = buildMagicLink(token, options.redirect);
  const magicLinkValidity = formatMagicLinkValidity(config.magicLinkExpirySeconds);
  const isNewUser = Boolean(options.isRegistration);
  const subject = isNewUser
    ? 'Complete your Wearables registration'
    : 'Your Wearables login link';

  if (shouldLogOnly) {
    logger.info('Magic link email suppressed (log-only mode)', {
      email,
      magicLink,
    });
    return;
  }

  const innerHtml = `
    <div style="background:#E8F3F8;padding:28px;border-radius:12px;margin-bottom:20px;">
      <h2 style="color:#0A1C3E;margin:0 0 16px 0;font-size:20px;font-weight:600;">
        ${isNewUser ? 'Welcome to Wearables' : 'Secure login'}
      </h2>
      <p style="color:#105067;margin:0 0 18px 0;font-size:15px;line-height:1.6;">
        ${isNewUser
          ? 'Click the button below to complete your registration.'
          : 'Click the button below to securely access your account.'}
      </p>
      <div style="text-align:center;margin:24px 0;">
        <a href="${magicLink}"
           style="display:inline-block;background:#1A3F6E;color:#FFFFFF;padding:12px 20px;text-decoration:none;border-radius:8px;font-weight:600;font-size:15px;">
          ${isNewUser ? 'Complete registration' : 'Log in'}
        </a>
      </div>
      <p style="color:#578494;margin:0;font-size:13px;text-align:center;">
        This link is valid for ${magicLinkValidity} and can only be used once.
      </p>
    </div>
    <div style="background:#FFFFFF;padding:16px;border-radius:8px;border:1px solid #D1E4F0;">
      <p style="color:#105067;margin:0;font-size:13px;line-height:1.5;">
        If you did not request this ${isNewUser ? 'registration' : 'login'}, you can ignore this email.
      </p>
    </div>
  `;

  await sendEmail(email, subject, getMagicLinkEmailTemplate(innerHtml));
}

export async function sendApprovalEmail(email: string) {
  const loginUrl = `${getFrontendUrl()}/login`;
  const subject = 'Your Wearables account is approved';

  if (shouldLogOnly) {
    logger.info('Approval email suppressed (log-only mode)', {
      email,
      loginUrl,
    });
    return;
  }

  const contentHtml = `
    <div style="background:#E8F3F8;padding:28px;border-radius:12px;margin-bottom:20px;">
      <h2 style="color:#0A1C3E;margin:0 0 16px 0;font-size:20px;font-weight:600;">
        You're approved
      </h2>
      <p style="color:#105067;margin:0 0 18px 0;font-size:15px;line-height:1.6;">
        Your Wearables account has been approved. You can now sign in using your email.
      </p>
      <div style="text-align:center;margin:24px 0;">
        <a href="${loginUrl}"
           style="display:inline-block;background:#1A3F6E;color:#FFFFFF;padding:12px 20px;text-decoration:none;border-radius:8px;font-weight:600;font-size:15px;">
          Go to login
        </a>
      </div>
      <p style="color:#578494;margin:0;font-size:13px;text-align:center;">
        If you did not request access, you can ignore this email.
      </p>
    </div>
  `;

  await sendEmail(email, subject, getEmailTemplate('Access approved', contentHtml));
}

function getEmailTemplate(title: string, contentHtml: string): string {
  return `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>${title}</title>
    </head>
    <body style="Margin:0;padding:0;background-color:#F7FBFF;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F7FBFF;">
        <tr>
          <td align="center" style="padding:20px 0;">
            <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%;background-color:#FFFFFF;border:1px solid #D1E4F0;border-radius:12px;padding:40px;">
              <tr>
                <td align="center" style="font-family:Arial,Helvetica,sans-serif;font-size:28px;font-weight:600;color:#1A3F6E;padding-bottom:20px;">Wearables</td>
              </tr>
              <tr>
                <td style="font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:600;color:#0A1C3E;padding-bottom:20px;text-align:center;">${title}</td>
              </tr>
              <tr>
                <td style="font-family:Arial,Helvetica,sans-serif;font-size:16px;color:#0A1C3E;line-height:1.5;">
                  ${contentHtml}
                </td>
              </tr>
              <tr>
                <td align="center" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#578494;padding-top:30px;">
                  © 2026 Wearables. All rights reserved.
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
  `;
}

function getMagicLinkEmailTemplate(contentHtml: string): string {
  return getEmailTemplate('Secure Access to Wearables', contentHtml);
}
