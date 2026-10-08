import { useCallback, useEffect, useMemo, useState } from 'react';
import { Copy, Eye, EyeOff } from 'lucide-react';
import { API_BASE_PATH, defaultApi, type ApiToken } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { StatusCallout } from '@/components/custom/StatusCallout';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { isAdminUser } from '@/lib/userAccess';

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—';

const maskedToken = (token: string) => `${token.slice(0, 4)}${'•'.repeat(Math.max(8, token.length - 4))}`;

function NewTokenPanel({ token, onDismiss }: { token: string; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(token);
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  };

  return (
    <div className="surface-subtle mt-4 rounded-xl p-3">
      <p className="m-0 text-sm text-foreground">
        Copy your new token now. We only store a fingerprint of it, so it cannot be shown again.
      </p>
      <div className="mt-3 flex items-center gap-2">
        <code
          className="block min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-xl border border-border bg-muted/40 px-3 py-2 text-sm text-foreground"
          aria-label="New API token"
        >
          {visible ? token : maskedToken(token)}
        </code>
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => setVisible((value) => !value)}
          aria-label={visible ? 'Hide token' : 'Show token'}
          title={visible ? 'Hide token' : 'Show token'}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </Button>
        <Button type="button" onClick={() => void handleCopy()}>
          <Copy className="mr-2 h-4 w-4" />
          {copied ? 'Copied' : 'Copy token'}
        </Button>
      </div>
      {copyError ? (
        <StatusCallout tone="error" message="Unable to copy the token. Show it and copy it manually." className="mt-3" />
      ) : null}
      <div className="mt-3">
        <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
          I have saved it
        </Button>
      </div>
    </div>
  );
}

function TokenTable({
  tokens,
  showOwner,
  busyId,
  onRevoke,
}: {
  tokens: ApiToken[];
  showOwner: boolean;
  busyId: string | null;
  onRevoke: (token: ApiToken) => void;
}) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase tracking-[0.08em] text-muted-foreground">
          <tr>
            <th className="py-2 pr-4 font-semibold">Name</th>
            {showOwner ? <th className="py-2 pr-4 font-semibold">Owner</th> : null}
            <th className="py-2 pr-4 font-semibold">Token</th>
            <th className="py-2 pr-4 font-semibold">Created</th>
            <th className="py-2 pr-4 font-semibold">Last used</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody>
          {tokens.map((token) => (
            <tr key={token.id} className="border-t border-border">
              <td className="py-2 pr-4">{token.name}</td>
              {showOwner ? <td className="py-2 pr-4">{token.owner_email}</td> : null}
              <td className="py-2 pr-4 font-mono text-xs">wrt_…{token.token_hint}</td>
              <td className="py-2 pr-4">{formatDate(token.created_at)}</td>
              <td className="py-2 pr-4">{formatDate(token.last_used_at)}</td>
              <td className="py-2 text-right">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={busyId === token.id}
                  onClick={() => onRevoke(token)}
                >
                  {busyId === token.id ? 'Revoking…' : 'Revoke'}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ResearcherApiAccessPage() {
  const { user } = useAuth();
  const isAdmin = isAdminUser(user);
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [allTokens, setAllTokens] = useState<ApiToken[]>([]);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [tokenName, setTokenName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const formattedBasePath = useMemo(() => API_BASE_PATH.replace(/\/$/, ''), []);
  const extractionBasePath = `${formattedBasePath}/extraction`;
  const extractionOrigin = formattedBasePath.startsWith('http') ? '' : window.location.origin;

  const loadTokens = useCallback(async () => {
    setError(null);
    try {
      const [own, all] = await Promise.all([
        defaultApi.listMyApiTokens(),
        isAdmin ? defaultApi.listAllApiTokens() : Promise.resolve<ApiToken[]>([]),
      ]);
      setTokens(own);
      setAllTokens(all);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load API tokens.');
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    void loadTokens();
  }, [loadTokens]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    const name = tokenName.trim();
    if (!name) return;
    setCreating(true);
    setError(null);
    try {
      const created = await defaultApi.createApiToken(name);
      setNewToken(created.token);
      setTokenName('');
      await loadTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create the API token.');
    } finally {
      setCreating(false);
    }
  };

  const handleRevoke = async (token: ApiToken, asAdmin: boolean) => {
    const owner = asAdmin && token.owner_email !== user?.email ? ` of ${token.owner_email}` : '';
    if (!window.confirm(`Revoke the token "${token.name}"${owner}? Scripts using it will stop working.`)) return;
    setBusyId(token.id);
    setError(null);
    try {
      await (asAdmin ? defaultApi.adminRevokeApiToken(token.id) : defaultApi.revokeMyApiToken(token.id));
      await loadTokens();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to revoke the API token.');
    } finally {
      setBusyId(null);
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
          <li>Create a personal token below and copy it.</li>
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
        <h2 className="text-section-title">Your API tokens</h2>
        <p className="m-0 mt-2 text-sm text-muted-foreground">
          Create one token per script or computer, so you can revoke it on its own if it leaks.
        </p>

        {error ? <StatusCallout tone="error" message={error} className="mt-4" /> : null}

        <form className="mt-4 flex flex-col gap-2 md:flex-row md:items-center" onSubmit={(event) => void handleCreate(event)}>
          <input
            type="text"
            placeholder="Token name, e.g. analysis laptop"
            value={tokenName}
            maxLength={100}
            onChange={(event) => setTokenName(event.target.value)}
            className="field-input ui-control-h w-full rounded-xl px-3 md:w-[20rem]"
            aria-label="Token name"
          />
          <Button type="submit" disabled={creating || !tokenName.trim()}>
            {creating ? 'Creating…' : 'Create token'}
          </Button>
        </form>

        {newToken ? <NewTokenPanel token={newToken} onDismiss={() => setNewToken(null)} /> : null}

        {loading ? (
          <p className="m-0 mt-4 text-sm text-muted-foreground">Loading tokens…</p>
        ) : tokens.length === 0 ? (
          <p className="m-0 mt-4 text-sm text-muted-foreground">You have no active tokens.</p>
        ) : (
          <TokenTable tokens={tokens} showOwner={false} busyId={busyId} onRevoke={(token) => void handleRevoke(token, false)} />
        )}
      </section>

      {isAdmin ? (
        <section className="surface-card mt-6 p-4 md:p-5">
          <h2 className="text-section-title">All active tokens</h2>
          <p className="m-0 mt-2 text-sm text-muted-foreground">As an admin you can revoke any researcher&apos;s token.</p>
          {loading ? null : allTokens.length === 0 ? (
            <p className="m-0 mt-4 text-sm text-muted-foreground">No active tokens.</p>
          ) : (
            <TokenTable tokens={allTokens} showOwner busyId={busyId} onRevoke={(token) => void handleRevoke(token, true)} />
          )}
        </section>
      ) : null}
    </>
  );
}
