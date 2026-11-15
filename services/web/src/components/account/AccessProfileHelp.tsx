import { useState } from 'react';
import { CircleHelp } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

export function AccessProfileHelp() {
  const [open, setOpen] = useState(false);

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip open={open} onOpenChange={setOpen}>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label="Explain access profiles"
            onClick={() => setOpen((current) => !current)}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <CircleHelp className="h-4 w-4" aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="right"
          align="center"
          collisionPadding={12}
          sideOffset={8}
          className="max-h-[var(--radix-tooltip-content-available-height)] w-[min(26rem,calc(100vw-2rem))] overflow-y-auto p-3 text-left text-sm"
        >
          <div className="flex flex-col gap-3 [&_p]:m-0">
            <p className="font-semibold">
              Choose the person's responsibilities
            </p>
            <dl className="space-y-2">
              <div>
                <dt className="font-semibold">Practitioner</dt>
                <dd>
                  Use the patient overview, case pages and Add Case. This keeps
                  the existing practitioner access from main.
                </dd>
              </div>
              <div>
                <dt className="font-semibold">Researcher</dt>
                <dd>
                  Use research/export APIs and manage personal API tokens.
                  Cannot open practitioner patient pages.
                </dd>
              </div>
              <div>
                <dt className="font-semibold">Practitioner + Researcher</dt>
                <dd>
                  Has both staff roles. Does not approve accounts or manage
                  other users.
                </dd>
              </div>
              <div>
                <dt className="font-semibold">Admin</dt>
                <dd>
                  Approve account and role requests, manage users, and use the
                  clinical and research areas.
                </dd>
              </div>
            </dl>
            <p className="border-t border-border pt-2 text-muted-foreground">
              New registrations require admin approval. Only approved accounts
              can use protected features.
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
