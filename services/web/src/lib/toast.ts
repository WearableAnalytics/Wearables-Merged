import { useEffect } from 'react';
import { toast } from 'sonner';

type ToastKind = 'error' | 'info' | 'success';

function showMessageToast(kind: ToastKind, id: string, message: string) {
  if (kind === 'error') {
    toast.error(message, { id });
    return;
  }

  if (kind === 'success') {
    toast.success(message, { id });
    return;
  }

  toast.info(message, { id });
}

export function useMessageToast(kind: ToastKind, id: string, message: string | null | undefined) {
  useEffect(() => {
    if (!message) {
      toast.dismiss(id);
      return;
    }

    showMessageToast(kind, id, message);
  }, [id, kind, message]);
}

export function useLoadingToast(id: string, isLoading: boolean, loadingMessage: string) {
  useEffect(() => {
    if (isLoading) {
      toast.loading(loadingMessage, { id });
      return;
    }

    toast.dismiss(id);
  }, [id, isLoading, loadingMessage]);
}
