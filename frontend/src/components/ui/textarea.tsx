import * as React from "react";
import { cn } from "../../lib/utils";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, onChange, ...props }, ref) => {
    // 自动增高：高度跟随内容，超过 max-h 后内部滚动
    const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      e.target.style.height = "auto";
      e.target.style.height = `${e.target.scrollHeight}px`;
      onChange?.(e);
    };
    return (
      <textarea
        className={cn(
          "flex min-h-[120px] max-h-64 w-full overflow-y-auto rounded-sm border border-border-default bg-bg-input px-3 py-3 text-sm text-text-primary",
          "placeholder:text-text-disabled",
          "resize-y break-all whitespace-pre-wrap",
          "focus:outline-none focus:border-purple-500 focus:ring-3 focus:ring-purple-500/15",
          "disabled:cursor-not-allowed disabled:bg-bg-gray disabled:text-text-disabled",
          className,
        )}
        ref={ref}
        onChange={handleChange}
        {...props}
      />
    );
  },
);
Textarea.displayName = "Textarea";

export { Textarea };