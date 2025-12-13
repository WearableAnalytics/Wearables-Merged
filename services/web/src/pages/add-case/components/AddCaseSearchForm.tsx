import type { FormEvent } from 'react';
import { Loader2, Search } from 'lucide-react';

type AddCaseSearchFormProps = {
  caseId: string;
  loading: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onChange: (value: string) => void;
  onFocusReset: () => void;
};

export function AddCaseSearchForm({
  caseId,
  loading,
  onSubmit,
  onChange,
  onFocusReset,
}: AddCaseSearchFormProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-4" aria-busy={loading}>
      <label className="sr-only" htmlFor="case-search">
        Search for a case by ID
      </label>
      <div className="relative flex items-center">
        <input
          id="case-search"
          type="search"
          inputMode="numeric"
          maxLength={200}
          placeholder="Enter Charité Case ID"
          value={caseId}
          onChange={(event) => onChange(event.target.value)}
          onFocus={onFocusReset}
          className="w-full rounded-full border border-slate-200 bg-white px-6 py-4 pr-16 text-lg shadow-[0_16px_40px_rgba(15,23,42,0.08)] outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200 disabled:cursor-not-allowed disabled:bg-slate-50"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading}
          className="absolute right-2 flex h-12 w-12 items-center justify-center rounded-full bg-black text-white transition-transform duration-200 hover:scale-[1.05] active:scale-50 disabled:opacity-80 disabled:hover:scale-100"
        >
          {loading ? <Loader2 aria-hidden className="h-5 w-5 animate-spin" /> : <Search aria-hidden className="h-5 w-5" />}
          <span className="sr-only">Search</span>
        </button>
      </div>
    </form>
  );
}
