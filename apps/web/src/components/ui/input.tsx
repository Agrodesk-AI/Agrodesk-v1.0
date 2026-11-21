import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "h-12 w-full rounded-xl border border-border bg-surface px-4 text-base outline-none placeholder:text-muted focus:border-primary focus:ring-2 focus:ring-primary/20",
          className,
        )}
        {...rest}
      />
    );
  },
);
