export function Modal({ children, onClose }) {
  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      {children}
    </div>
  );
}
