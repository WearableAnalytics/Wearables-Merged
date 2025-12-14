import type { CaseCreated, ChariteCase } from '@/api/openapi-client';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { InfoItem } from './InfoItem';

type AddCaseResultCardProps = {
  caseData: ChariteCase;
  creating: boolean;
  created: CaseCreated | null;
  createError: string | null;
  formatDate: (value: ChariteCase['birthDate']) => string;
  onCreate: () => void;
};

export function AddCaseResultCard({
  caseData,
  creating,
  created,
  createError,
  formatDate,
  onCreate,
}: AddCaseResultCardProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_12px_30px_rgba(15,23,42,0.06)]">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="m-0 text-sm font-semibold uppercase tracking-[0.08em] text-slate-500">Charité case</p>
          <h3 className="m-0 text-[22px] font-semibold text-slate-900">
            {caseData.firstName} {caseData.lastName}
          </h3>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 px-3 py-1 font-mono text-sm tracking-[0.02em] text-slate-700">
          ID
          <span className="font-semibold text-slate-900">{caseData.cCaseId}</span>
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <InfoItem label="First name" value={caseData.firstName} />
        <InfoItem label="Last name" value={caseData.lastName} />
        <InfoItem label="Date of birth" value={formatDate(caseData.birthDate)} />
        <InfoItem label="Charité Case ID" value={caseData.cCaseId} />
      </dl>

      <div className="mt-4 flex flex-col gap-3">
        <Button
          type="button"
          disabled={creating}
          onClick={onCreate}
          className="w-full rounded-xl px-4 py-3 text-base font-semibold transition hover:scale-[1.01] focus-visible:ring-black active:scale-95"
        >
          {creating ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : null}
          Add case to system
        </Button>

        {createError ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700">
            {createError}
          </div>
        ) : null}

        {created ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
            <p className="m-0 font-semibold">Case created</p>
            <ul className="m-1 ml-4 list-disc space-y-1">
              <li>
                Patient ID:{' '}
                <span className="font-mono font-semibold tracking-[0.02em] text-emerald-800">{created.patientId}</span>
              </li>
              <li>
                Case ID:{' '}
                <span className="font-mono font-semibold tracking-[0.02em] text-emerald-800">{created.caseId}</span>
              </li>
              <li>
                Case token:{' '}
                <span className="font-mono font-semibold tracking-[0.02em] text-emerald-800">{created.caseToken}</span>
              </li>
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
