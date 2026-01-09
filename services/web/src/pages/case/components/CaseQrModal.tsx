import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import QRCode from 'qrcode';

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 px-4 backdrop-blur-sm"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="relative w-full max-w-[420px] rounded-2xl bg-white p-6 shadow-[0_24px_60px_rgba(15,23,42,0.18)]"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 inline-flex h-9 w-9 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 focus:ring-offset-white"
          aria-label="Close QR code"
        >
          <X aria-hidden className="h-5 w-5" />
        </button>
        <div className="flex flex-col items-center gap-3">
          <p className="m-0 text-center text-sm font-semibold uppercase tracking-[0.08em] text-slate-500">
            Case access QR
          </p>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <canvas
              ref={qrCanvasRef}
              className="h-[320px] w-[320px]"
              aria-label="Case access QR code expanded view"
            />
          </div>
          <p className="m-0 text-center text-xs text-slate-600">Tap outside the QR code to close.</p>
        </div>
      </div>
    </div>
  );
}
