import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/custom/PageHeader';
import { StatusCallout, type StatusTone } from '@/components/custom/StatusCallout';
import {
  LOGOUT_REASON_EXPIRED,
  LOGOUT_REASON_QUERY_PARAM,
  LOGOUT_REASON_SUCCESS,
} from '@/lib/authSession';

type LogoutContent = {
  title: string;
  description: string;
  cardMessage: string;
  tone: StatusTone;
};

export function LogoutPage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get(LOGOUT_REASON_QUERY_PARAM);

  const content = useMemo<LogoutContent>(() => {
    if (reason === LOGOUT_REASON_EXPIRED) {
      return {
        title: 'Session expired',
        description: 'Your session expired. Please log in again to continue.',
        cardMessage: 'Please sign in again from the login page.',
        tone: 'warning',
      };
    }

    if (reason === LOGOUT_REASON_SUCCESS) {
      return {
        title: 'You have been logged out',
        description: 'You logged out successfully.',
        cardMessage: 'Use the login page when you want to sign back in.',
        tone: 'info',
      };
    }

    return {
      title: 'You have been logged out',
      description: 'Your session has ended. Please log in again.',
      cardMessage: 'Use the login page to sign back in.',
      tone: 'info',
    };
  }, [reason]);

  return (
    <>
      <PageHeader
        label="Logout"
        title={content.title}
        description={content.description}
      />

      <div className="mt-6">
        <StatusCallout tone={content.tone} message={content.cardMessage} />
      </div>
    </>
  );
}
