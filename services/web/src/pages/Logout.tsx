import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '@/components/custom/PageHeader';
import { SignedInAs } from '@/components/custom/SignedInAs';
import {
  LOGOUT_REASON_EXPIRED,
  LOGOUT_REASON_QUERY_PARAM,
  LOGOUT_REASON_SUCCESS,
} from '@/lib/authSession';

export function LogoutPage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get(LOGOUT_REASON_QUERY_PARAM);

  const content = useMemo(() => {
    if (reason === LOGOUT_REASON_EXPIRED) {
      return {
        title: 'Session expired',
        description: 'Your session expired. Please log in again to continue.',
        cardMessage: 'Please sign in again from the access page.',
      };
    }

    if (reason === LOGOUT_REASON_SUCCESS) {
      return {
        title: 'You have been logged out',
        description: 'You logged out successfully.',
        cardMessage: 'Use the access page when you want to sign back in.',
      };
    }

    return {
      title: 'You have been logged out',
      description: 'Your session has ended. Please log in again.',
      cardMessage: 'Use the access page to sign back in.',
    };
  }, [reason]);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        label="Logout"
        title={content.title}
        description={content.description}
      />
      <SignedInAs />

      <div className="surface-card p-5">
        <p className="m-0 text-muted-foreground">{content.cardMessage}</p>
      </div>
    </div>
  );
}
