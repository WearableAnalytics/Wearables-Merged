import { QrCode } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Props = {
  caseToken: string | null | undefined;
  onOpen: () => void;
};

export function CaseQrCard({ caseToken, onOpen }: Props) {
  return (
    <div className="surface-card flex w-full items-center justify-between gap-3 p-3">
      <div className="flex flex-col gap-1">
        <p className="m-0 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">Access for app</p>
        <p className="m-0 text-sm font-medium text-muted-foreground">Scan with Wearables app</p>
      </div>
      <div className="flex items-center">
        {caseToken ? (
          <Button
            type="button"
            onClick={onOpen}
            variant="outline"
            className="px-3 font-semibold"
          >
            <QrCode aria-hidden className="h-5 w-5 text-muted-foreground" />
            <span>Show QR</span>
          </Button>
        ) : (
          <div className="surface-subtle px-3 py-2 text-sm text-muted-foreground">
            No token available
          </div>
        )}
      </div>
    </div>
  );
}
