import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const tones = {
  default: "bg-black/5 text-text",
  hot: "bg-accent/20 text-accent",
  warm: "bg-secondary/20 text-text",
  dead: "bg-black/10 text-muted",
  danger: "bg-danger/10 text-danger",
  primary: "bg-primary/10 text-primary",
} as const;

export function Badge({
  tone = "default",
  className,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
      {...rest}
    />
  );
}
