import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";

/**
 * Brief confirmation toasts — for "saved"/"sent" signals only. Errors that
 * require an action must stay persistent next to the work (ui-banner /
 * field error); never route them through here to disappear.
 */
export type ToastTone = "success" | "info";

type Toast = { id: number; tone: ToastTone; message: string };

const ToastContext = createContext<{ notify: (message: string, tone?: ToastTone) => void }>({
  notify: () => {},
});

export function useToast(): { notify: (message: string, tone?: ToastTone) => void } {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: PropsWithChildren): JSX.Element {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const notify = useCallback((message: string, tone: ToastTone = "success") => {
    const id = nextId.current++;
    setToasts((current) => [...current.slice(-3), { id, tone, message }]);
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id));
    }, 4200);
  }, []);

  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="ui-toast-region">
        {toasts.map((toast) => (
          <div className={`ui-toast ui-toast--${toast.tone}`} key={toast.id} role="status">
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
