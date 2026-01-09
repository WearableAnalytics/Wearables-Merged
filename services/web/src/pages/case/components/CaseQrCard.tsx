import { QrCode } from 'lucide-react';

type Props = {
  caseToken: string | null | undefined;
  onOpen: () => void;
};

export function CaseQrCard({ caseToken, onOpen }: Props) {
  return (
    <div className="w-full rounded-2xl border border-slate-200 bg-white shadow-[0_12px_30px_rgba(15,23,42,0.06)] p-3 flex items-center justify-between gap-3">
      <div className="flex flex-col gap-1">
        <p className="m-0 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500">Access for app</p>
        <p className="m-0 text-sm font-medium text-slate-700">Scan with Wearables app</p>
      </div>
      <div className="flex items-center">
        {caseToken ? (
          <button
            type="button"
            onClick={onOpen}
            className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 focus:ring-offset-white"
          >
            <QrCode aria-hidden className="h-5 w-5 text-slate-700" />
            <span>Show QR</span>
          </button>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
            No token available
          </div>
        )}
      </div>
    </div>
  );
}
