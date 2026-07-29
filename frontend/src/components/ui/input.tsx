import * as React from "react";
import { cn } from "../../lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-8 w-full rounded-sm border border-border-default bg-white px-3 py-2 text-sm text-text-primary",
          "placeholder:text-text-disabled",
          "focus:outline-none focus:border-purple-500 focus:ring-3 focus:ring-purple-500/15",
          "disabled:cursor-not-allowed disabled:bg-bg-gray disabled:text-text-disabled",
          "file:border-0 file:bg-transparent file:text-sm file:font-medium",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };