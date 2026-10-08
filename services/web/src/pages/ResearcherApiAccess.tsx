import { useEffect, useMemo, useState } from 'react';
import { API_BASE_PATH, defaultApi } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { StatusCallout } from '@/components/custom/StatusCallout';
import { Button } from '@/components/ui/button';

export function ResearcherApiAccessPage() {
  const [apiAccessToken, setApiAccessToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const formattedBasePath = useMemo(() => API_BASE_PATH.replace(/\/$/, ''), []);
  const extractionBasePath = `${formattedBasePath}/extraction`;
  const extractionOrigin = formattedBasePath.startsWith('http') ? '' : window.location.origin;

  useEffect(() => {
    let cancelled = false;

    const loadToken = async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await defaultApi.getResearcherApiAccessToken();
        if (!cancelled) {
          setApiAccessToken(data.apiAccessToken);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Unable to load API access token.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadToken();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCopyToken = async () => {
    if (!apiAccessToken) {
      return;
    }
    try {
      await navigator.clipboard.writeText(apiAccessToken);
      setCopied(true);
    } catch {
      setCopied(false);
      setError('Unable to copy token. Please copy it manually.');
    }
  };

  return (
    <>
      <PageHeader
        label="Researcher"
        title="API Access"
        description="Use this page to authenticate against research endpoints and test requests from your local tooling."
      />

      <section className="surface-card p-4 md:p-5">
        <h2 className="text-section-title">How to use the API</h2>
        <ol className="m-0 mt-3 list-decimal space-y-2 pl-5 text-sm text-foreground">
          <li>Copy your token from the section below.</li>
          <li>Call the export endpoints under <span className="font-mono">{extractionBasePath}</span>.</li>
          <li>Send the token as a bearer token in the <span className="font-mono">Authorization</span> header.</li>
        </ol>

        <p className="m-0 mt-3 text-sm text-foreground">
          All endpoints are documented in the{' '}
          <a className="underline" href={`${extractionBasePath}/docs`} target="_blank" rel="noreferrer">
            interactive API documentation
          </a>{' '}
          (OpenAPI spec at <span className="font-mono">{extractionBasePath}/openapi.json</span>), where you can also try
          them out while logged in.
        </p>

        <div className="surface-subtle mt-4 rounded-xl p-3">
          <p className="m-0 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Example</p>
          <pre className="m-0 mt-2 overflow-x-auto text-xs text-foreground">
{`curl -G "${extractionOrigin}${extractionBasePath}/v1/measurements/export.csv" \\
  -d patient_id=<patient-id> -d measurement=heart-rate \\
  -H "Authorization: Bearer <your-token>" -o heart-rate.csv`}
          </pre>
        </div>
      </section>

      <section className="surface-card mt-6 p-4 md:p-5">
        <h2 className="text-section-title">Your API access token</h2>

        {error ? <StatusCallout tone="error" message={error} className="mt-4" /> : null}

        {loading ? (
          <p className="m-0 mt-4 text-sm text-muted-foreground">Loading token…</p>
        ) : (
          <div className="mt-4 flex flex-col gap-3">
            <code className="block overflow-x-auto rounded-xl border border-border bg-muted/40 px-3 py-2 text-sm text-foreground">
              {apiAccessToken ?? 'No token available.'}
            </code>
            <div>
              <Button type="button" onClick={() => void handleCopyToken()} disabled={!apiAccessToken}>
                {copied ? 'Copied' : 'Copy token'}
              </Button>
            </div>
          </div>
        )}
      </section>
    </>
  );
}
