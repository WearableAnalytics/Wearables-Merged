import { useLocation } from 'react-router-dom';
import { PageHeader } from '@/components/custom/PageHeader';
import { StatusCallout, type StatusTone } from '@/components/custom/StatusCallout';

type RequestSentState = {
  title?: string;
  description?: string;
  message?: string;
  tone?: StatusTone;
};

export function AuthRequestSentPage() {
  const location = useLocation();
  const state = (location.state ?? {}) as RequestSentState;

  const title = state.title ?? 'Request received';
  const description =
    state.description ?? 'If your request is approved, you will receive an email with next steps.';
  const message =
    state.message ?? 'Thanks. If your email is eligible, we will reach out shortly.';
  const tone = state.tone ?? 'info';

  return (
    <>
      <PageHeader label="Status" title={title} description={description} />

      <div className="mt-6">
        <StatusCallout tone={tone} message={message} />
      </div>
    </>
  );
}
