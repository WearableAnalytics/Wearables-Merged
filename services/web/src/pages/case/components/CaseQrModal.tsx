import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import QRCode from 'qrcode';
import { Button } from '@/components/ui/button';

type Props = {
  isOpen: boolean;
  caseToken: string | null | undefined;
  onClose: () => void;
};

export function CaseQrModal({ isOpen, caseToken, onClose }: Props) {
  const qrCanvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!isOpen || !caseToken || !qrCanvasRef.current) return;

    const dpr = window.devicePixelRatio || 1;
    const targetSize = 320;
    const renderSize = Math.floor(targetSize * dpr);
    const canvasEl = qrCanvasRef.current;

    QRCode.toCanvas(canvasEl, caseToken, {
      width: renderSize,
      margin: 0,
      color: {
        dark: '#0f172a',
        light: '#ffffff',
      },
    })
      .then(() => {
        canvasEl.style.width = `${targetSize}px`;
        canvasEl.style.height = `${targetSize}px`;
      })
      .catch(() => {
        /* noop: keep silent if QR rendering fails */
      });
  }, [caseToken, isOpen]);

  if (!isOpen || !caseToken) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[hsl(var(--slate-900)/0.7)] px-4 backdrop-blur-sm"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="relative w-full max-w-[420px] rounded-2xl border border-border bg-card p-6 shadow-[var(--shadow-modal)]"
        onClick={(event) => event.stopPropagation()}
      >
        <Button
          type="button"
          onClick={onClose}
          variant="ghost"
          size="icon"
          className="absolute right-4 top-4 rounded-full text-muted-foreground hover:bg-transparent active:bg-transparent hover:text-foreground"
          aria-label="Close QR code"
        >
          <X aria-hidden className="h-5 w-5" />
        </Button>
        <div className="flex flex-col items-center gap-3">
          <p className="m-0 text-center text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Case access QR
          </p>
          <div className="surface-subtle rounded-2xl p-4">
            <canvas
              ref={qrCanvasRef}
              className="h-[320px] w-[320px]"
              aria-label="Case access QR code expanded view"
            />
          </div>
          <p className="m-0 text-center text-xs text-muted-foreground">Tap outside the QR code to close.</p>
        </div>
      </div>
    </div>
  );
}
