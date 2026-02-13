import type { FormEvent } from 'react';
import { ArrowRight } from 'lucide-react';
import { PageHeader } from '@/components/custom/PageHeader';
import { SearchForm } from '@/components/custom/SearchForm';

type AuthEmailFormPageProps = {
  headerLabel: string;
  headerTitle: string;
  headerDescription: string;
  email: string;
  loading: boolean;
  inputId: string;
  submitLabel: string;
  onEmailChange: (value: string) => void;
  onFocusReset: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function AuthEmailFormPage({
  headerLabel,
  headerTitle,
  headerDescription,
  email,
  loading,
  inputId,
  submitLabel,
  onEmailChange,
  onFocusReset,
  onSubmit,
}: AuthEmailFormPageProps) {
  return (
    <>
      <PageHeader label={headerLabel} title={headerTitle} description={headerDescription} />

      <div className="flex min-h-[70vh] items-start justify-center pt-8 md:pt-12">
        <div className="w-full max-w-3xl px-4">
          <SearchForm
            value={email}
            loading={loading}
            onChange={onEmailChange}
            onFocusReset={onFocusReset}
            onSubmit={onSubmit}
            inputId={inputId}
            inputLabel="Email address"
            inputType="email"
            inputMode="email"
            autoComplete="email"
            placeholder="Enter your email address"
            submitIcon={<ArrowRight aria-hidden className="h-5 w-5" />}
            submitLabel={submitLabel}
          />
        </div>
      </div>
    </>
  );
}
