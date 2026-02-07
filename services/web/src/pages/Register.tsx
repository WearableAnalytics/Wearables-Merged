import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { defaultApi, isDirectAuthResponse } from '@/api/defaultApi';
import { PageHeader } from '@/components/custom/PageHeader';
import { SearchForm } from '@/components/custom/SearchForm';
import { ArrowRight } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

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
    const trimmedEmail = email.trim();

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
    <>
      <PageHeader
        label="Register"
        title="Request access"
        description="Enter your email to request access. You will be notified after approval."
      />

      <div className="flex min-h-[70vh] items-start justify-center pt-8 md:pt-12">
        <div className="w-full max-w-3xl px-4">
          <SearchForm
            value={email}
            loading={loading}
            onChange={(value) => setEmail(value)}
            onFocusReset={resetFeedback}
            onSubmit={handleRegister}
            inputId="register-email"
            inputLabel="Email address"
            inputType="email"
            inputMode="email"
            autoComplete="email"
            placeholder="Enter your email address"
            submitIcon={<ArrowRight aria-hidden className="h-5 w-5" />}
            submitLabel="Request access"
          />
        </div>
      </div>
    </>
  );
}
