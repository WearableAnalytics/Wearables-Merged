import type { FormEvent, InputHTMLAttributes, ReactNode } from 'react';
import { Loader2, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';

type SearchFormProps = {
  value: string;
  loading: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onChange: (value: string) => void;
  onFocusReset: () => void;
  inputId?: string;
  inputLabel?: string;
  inputType?: string;
  inputMode?: InputHTMLAttributes<HTMLInputElement>['inputMode'];
  placeholder?: string;
  submitIcon?: ReactNode;
  submitLabel?: string;
  autoComplete?: string;
};

export function SearchForm({
  value,
  loading,
  onSubmit,
  onChange,
  onFocusReset,
  inputId = 'search-input',
  inputLabel = 'Search',
  inputType = 'search',
  inputMode = 'text',
  placeholder = 'Enter a value',
  submitIcon,
  submitLabel = 'Search',
  autoComplete = 'off',
}: SearchFormProps) {
  return (
    <form onSubmit={onSubmit} className="space-y-4" aria-busy={loading}>
      <label className="sr-only" htmlFor={inputId}>
        {inputLabel}
      </label>
      <div className="relative flex items-center">
        <input
          id={inputId}
          type={inputType}
          inputMode={inputMode}
          maxLength={200}
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onFocus={onFocusReset}
          className={inputType === 'search' ? 'field-input-pill field-input-pill-search' : 'field-input-pill'}
          disabled={loading}
          autoComplete={autoComplete}
        />
        <Button
          type="submit"
          disabled={loading}
          size="icon"
          searchBehavior
          className="absolute right-2 rounded-full"
        >
          {loading ? (
            <Loader2 aria-hidden className="h-5 w-5 animate-spin" />
          ) : (
            submitIcon ?? <Search aria-hidden className="h-5 w-5" />
          )}
          <span className="sr-only">{submitLabel}</span>
        </Button>
      </div>
    </form>
  );
}
