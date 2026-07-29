import * as React from "react";
import { cn } from "../../lib/utils";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        className={cn(
          "flex min-h-[120px] w-full rounded-sm border border-border-default bg-bg-input px-3 py-3 text-sm text-text-primary",
          "placeholder:text-text-disabled",
          "focus:outline-none focus:border-purple-500 focus:ring-3 focus:ring-purple-500/15",
          "disabled:cursor-not-allowed disabled:bg-bg-gray disabled:text-text-disabled",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };