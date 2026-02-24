import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { defaultApi, isDirectAuthResponse, type NonAdminRole } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { AuthEmailFormPage } from '@/components/custom/AuthEmailFormPage';
import { Button } from '@/components/ui/button';
import { getTrimmedOrNull } from '@/lib/input';
import { getDefaultAuthenticatedPath } from '@/lib/userAccess';
import { useMessageToast } from '@/lib/toast';

const ROLE_OPTIONS: Array<{ value: NonAdminRole; label: string; description: string }> = [
  {
    value: 'practitioner',
    label: 'Practitioner',
    description: 'Access patient and case workflows.',
  },
  {
    value: 'researcher',
    label: 'Researcher',
    description: 'Access researcher API.',
  },
];

export function RegisterPage() {
  const navigate = useNavigate();
  const { user, loading: authLoading, refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [requestedRole, setRequestedRole] = useState<NonAdminRole | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useMessageToast('error', 'register-error', error);

  useEffect(() => {
    if (!authLoading && user) {
      navigate(getDefaultAuthenticatedPath(user), { replace: true });
    }
  }, [authLoading, navigate, user]);

  const resetFeedback = () => {
    setError(null);
  };

  const handleRegister = async (event: FormEvent) => {
    event.preventDefault();
    if (!requestedRole) {
      setError('Please choose a role.');
      return;
    }

    const trimmedEmail = getTrimmedOrNull(email);

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await defaultApi.register(trimmedEmail, requestedRole);
      if (isDirectAuthResponse(data)) {
        await refreshUser();
        navigate('/overview', { replace: true });
        return;
      }
      const successMessage =
        (data as { message?: string }).message ?? 'Your account is awaiting admin approval.';
      const requestSentTone = /magic link sent/i.test(successMessage) ? 'success' : 'info';
      navigate('/request-sent', {
        replace: true,
        state: {
          title: 'Request submitted',
          description: 'We will review your request and email you with next steps.',
          message: successMessage,
          tone: requestSentTone,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to register.');
    } finally {
      setLoading(false);
    }
  };

  const selectedRoleDescription =
    ROLE_OPTIONS.find((option) => option.value === requestedRole)?.description ?? ROLE_OPTIONS[0].description;

  return (
    <AuthEmailFormPage
      headerLabel="Register"
      headerTitle="Request access"
      headerDescription="Enter your email and choose your role."
      showForm={requestedRole !== null}
      preForm={
        <div className="space-y-2 text-center">
          <p className="m-0 text-sm font-semibold text-foreground">Choose your role</p>
          <div className="mx-auto grid w-1/2 grid-cols-2 gap-2">
            {ROLE_OPTIONS.map((option) => {
              const isActive = requestedRole === option.value;
              return (
                <Button
                  key={option.value}
                  type="button"
                  size="default"
                  variant={isActive ? 'default' : 'outline'}
                  className="w-full"
                  aria-pressed={isActive}
                  onClick={() => setRequestedRole(option.value)}
                >
                  {option.label}
                </Button>
              );
            })}
          </div>
          <p className="m-0 text-sm text-muted-foreground">{selectedRoleDescription}</p>
        </div>
      }
      email={email}
      loading={loading}
      onEmailChange={setEmail}
      onFocusReset={resetFeedback}
      onSubmit={handleRegister}
      inputId="register-email"
      submitLabel="Request access"
      footer={
        <p className="m-0 w-full text-center text-sm text-muted-foreground">
          Already registered?{' '}
          <Link to="/login" className="font-semibold text-foreground underline-offset-2 hover:underline">
            Go to login
          </Link>
          .
        </p>
      }
    />
  );
}
