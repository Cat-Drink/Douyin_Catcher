import { cn } from "../../lib/utils";
import { useToastStore } from "../../store/toastStore";
import type { ToastType } from "../../store/toastStore";

const iconMap: Record<ToastType, string> = {
  success: "✓",
  info: "ℹ",
  warning: "⚠",
  error: "✕",
};

const bgMap: Record<ToastType, string> = {
  success: "bg-success",
  info: "bg-text-primary",
  warning: "bg-warning text-white",
  error: "bg-error",
};

export function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 items-center">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            "flex items-center gap-2 h-10 px-4 py-2 rounded-sm text-white text-sm shadow-lg",
            "animate-in slide-in-from-bottom-2 fade-in duration-200",
            bgMap[toast.type],
          )}
          onClick={() => removeToast(toast.id)}
        >
          <span className="text-base">{iconMap[toast.type]}</span>
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
}