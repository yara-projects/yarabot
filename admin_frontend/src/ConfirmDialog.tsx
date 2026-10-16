import { useEffect, useRef } from 'react';

export function ConfirmDialog({ message, confirm, cancel }: { message: string; confirm: () => void; cancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { const element = dialog.current!; element.showModal(); return () => element.close(); }, []);
  return <dialog ref={dialog} className="editor-dialog" aria-labelledby="confirmation-title" onCancel={event => { event.preventDefault(); cancel(); }}>
    <div className="dialog-heading"><h2 id="confirmation-title">Confirm document action</h2></div>
    <p className="panel-padding">{message}</p>
    <div className="dialog-footer"><button className="button secondary" onClick={cancel}>Cancel</button><button className="button primary" onClick={confirm}>Confirm action</button></div>
  </dialog>;
}
