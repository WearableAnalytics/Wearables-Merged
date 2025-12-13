import { PageHeader } from '@/components/custom/PageHeader';
import { Search } from 'lucide-react';

export function NewCasePage() {
  return (
    <>
      <PageHeader
        label="New Case"
        title="Create a New Case"
        description="Search for an existing Charité case by ID."
      />

      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="w-full max-w-3xl px-4">
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
              className="w-full rounded-full border border-slate-200 bg-white px-6 py-4 pr-16 text-lg shadow-[0_16px_40px_rgba(15,23,42,0.08)] outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200"
            />
            <button
              type="button"
              className="absolute right-2 flex h-12 w-12 items-center justify-center rounded-full bg-black text-white transition-transform duration-200 hover:scale-[1.05] active:scale-95"
            >
              <Search aria-hidden className="h-5 w-5" />
              <span className="sr-only">Search</span>
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
