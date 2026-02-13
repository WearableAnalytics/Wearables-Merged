import type { ChariteCase } from '@/api/openapi-client';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { InfoItem } from '../../../components/custom/InfoItem';
import { formatDateDayMonthYear } from '@/lib/date';

type AddCaseResultCardProps = {
  caseData: ChariteCase;
  creating: boolean;
  onCreate: () => void;
};

export function AddCaseResultCard({
  caseData,
  creating,
  onCreate,
}: AddCaseResultCardProps) {
  return (
    <div className="surface-card p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="m-0 text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">Charite case</p>
          <h3 className="text-section-title">
            {caseData.firstName} {caseData.lastName}
          </h3>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 font-mono text-sm tracking-[0.02em] text-muted-foreground">
          ID
          <span className="font-semibold text-foreground">{caseData.cCaseId}</span>
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <InfoItem label="First name" value={caseData.firstName} />
        <InfoItem label="Last name" value={caseData.lastName} />
        <InfoItem label="Date of birth" value={formatDateDayMonthYear(caseData.birthDate)} />
        <InfoItem label="Charité Case ID" value={caseData.cCaseId} />
      </dl>

      <div className="mt-4 flex flex-col gap-3">
        <Button type="button" disabled={creating} onClick={onCreate} className="self-center text-base font-semibold">
          {creating ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : null}
          Add case to system
        </Button>
      </div>
    </div>
  );
}


