import { cn } from "../../lib/utils";

interface ToastProps {
  message: string;
  type?: "success" | "info" | "warning";
  visible: boolean;
}

const iconMap = {
  success: "✓",
  info: "ℹ",
  warning: "⚠",
};

export function Toast({ message, type = "info", visible }: ToastProps) {
  return (
    <div
      className={cn(
        "fixed bottom-6 left-1/2 -translate-x-1/2 z-50",
        "flex items-center gap-2 h-10 px-4 py-2 rounded-sm",
        "bg-text-primary text-white text-sm",
        "transition-all duration-200",
        visible ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0 pointer-events-none",
      )}
    >
      <span className="text-base">{iconMap[type]}</span>
      <span>{message}</span>
    </div>
  );
}