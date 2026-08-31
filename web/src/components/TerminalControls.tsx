import { ChevronDown } from "lucide-react";
import type {
  ButtonHTMLAttributes,
  PropsWithChildren,
  SelectHTMLAttributes,
} from "react";
import { Link, type LinkProps } from "react-router-dom";

type ControlTone = "default" | "primary";

interface TerminalButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: ControlTone;
}

interface TerminalLinkProps extends Omit<LinkProps, "className"> {
  className?: string;
  tone?: ControlTone;
}

interface TerminalSelectProps
  extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  wrapperClassName?: string;
}

export function TerminalButton({
  children,
  className,
  tone = "default",
  type = "button",
  ...props
}: PropsWithChildren<TerminalButtonProps>) {
  return (
    <button
      {...props}
      type={type}
      className={controlClassName(tone, className)}
      data-terminal-control="button"
    >
      <span className="terminal-control-content">{children}</span>
    </button>
  );
}

export function TerminalLink({
  children,
  className,
  tone = "default",
  ...props
}: PropsWithChildren<TerminalLinkProps>) {
  return (
    <Link
      {...props}
      className={controlClassName(tone, className)}
      data-terminal-control="link"
    >
      <span className="terminal-control-content">{children}</span>
    </Link>
  );
}

export function TerminalSelect({
  children,
  className,
  label,
  wrapperClassName,
  ...props
}: PropsWithChildren<TerminalSelectProps>) {
  return (
    <span
      className={[
        "terminal-select",
        wrapperClassName,
      ]
        .filter(Boolean)
        .join(" ")}
      data-terminal-control="select"
    >
      <select
        {...props}
        aria-label={label}
        className={["terminal-select-input", className]
          .filter(Boolean)
          .join(" ")}
      >
        {children}
      </select>
      <ChevronDown aria-hidden="true" className="terminal-select-icon" />
    </span>
  );
}

function controlClassName(
  tone: ControlTone,
  className?: string,
): string {
  return [
    "terminal-control",
    `terminal-control-${tone}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");
}
