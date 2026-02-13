import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { defaultApi, isDirectAuthResponse } from '@/api/defaultApi';
import { useAuth } from '@/context/AuthContext';
import { AuthEmailFormPage } from '@/components/custom/AuthEmailFormPage';
import { getTrimmedOrNull } from '@/lib/input';

export function RegisterPage() {
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (error) {
      toast.error(error, { id: 'register-error' });
    } else {
      toast.dismiss('register-error');
    }
  }, [error]);

  useEffect(() => {
    if (loading) {
      toast.loading('Submitting access request…', { id: 'register-loading' });
    } else {
      toast.dismiss('register-loading');
    }
  }, [loading]);

  const resetFeedback = () => {
    setError(null);
  };

  const handleRegister = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedEmail = getTrimmedOrNull(email);

    if (!trimmedEmail) {
      setError('Please enter your email address.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await defaultApi.register(trimmedEmail);
      if (isDirectAuthResponse(data)) {
        await refreshUser();
        navigate('/overview', { replace: true });
        return;
      }
      const successMessage =
        (data as { message?: string }).message ?? 'Your account is awaiting admin approval.';
      navigate('/request-sent', {
        replace: true,
        state: {
          title: 'Request submitted',
          description: 'We will review your request and email you with next steps.',
          message: successMessage,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to register.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthEmailFormPage
      headerLabel="Register"
      headerTitle="Request access"
      headerDescription="Enter your email to request access. You will be notified after approval."
      email={email}
      loading={loading}
      onEmailChange={setEmail}
      onFocusReset={resetFeedback}
      onSubmit={handleRegister}
      inputId="register-email"
      submitLabel="Request access"
    />
  );
}
