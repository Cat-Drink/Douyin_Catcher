import * as React from "react";
import { cn } from "../../lib/utils";

const Progress = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value?: number; variant?: "default" | "success" | "error" | "paused" }
>(({ className, value = 0, variant = "default", ...props }, ref) => {
  const barColor = {
    default: "bg-purple-500",
    success: "bg-success",
    error: "bg-error",
    paused: "bg-text-disabled",
  }[variant];

  return (
    <div
      ref={ref}
      className={cn("relative h-2 w-full overflow-hidden rounded-full bg-border-light", className)}
      {...props}
    >
      <div
        className={cn("h-full rounded-full transition-all duration-200 ease-out", barColor)}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
});
Progress.displayName = "Progress";

export { Progress };