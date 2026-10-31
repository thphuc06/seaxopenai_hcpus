import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export function Dialog({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    dialog?.showModal();
    return () => { dialog?.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={ref} className={`dialog ${wide ? 'dialog-wide' : ''}`} aria-labelledby="dialog-title"
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <header className="dialog-header"><h2 id="dialog-title">{title}</h2><button type="button" onClick={onClose} autoFocus aria-label="Close dialog">Close <span aria-hidden="true">×</span></button></header>
    <div className="dialog-body">{children}</div>
  </dialog>;
}
