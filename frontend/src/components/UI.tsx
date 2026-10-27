import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean; fullWidth?: boolean };

export function PrimaryButton({ loading = false, fullWidth = true, disabled, className = '', children, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      type={props.type ?? 'button'}
      className={`primary-button ${fullWidth ? 'full-width' : ''} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? '처리 중…' : children}
    </button>
  );
}

type CardProps = HTMLAttributes<HTMLDivElement> & { children: ReactNode };

export function Card({ className = '', children, ...props }: CardProps) {
  return <div {...props} className={`card ${className}`}>{children}</div>;
}

type ProgressBarProps = { value: number; max: number; label?: string; tone?: 'teal' | 'orange' };

export function ProgressBar({ value, max, label, tone = 'teal' }: ProgressBarProps) {
  const safeMax = Math.max(max, 1);
  const safeValue = Math.min(Math.max(value, 0), safeMax);
  return (
    <div className={`progress-wrap progress-${tone}`}>
      {label ? <div className="progress-label">{label}</div> : null}
      <div className="progress-track" role="progressbar" aria-label={label ?? '진행률'} aria-valuemin={0} aria-valuemax={safeMax} aria-valuenow={safeValue}>
        <span className="progress-fill" style={{ width: `${(safeValue / safeMax) * 100}%` }} />
      </div>
    </div>
  );
}

type BadgeProps = { children: ReactNode; tone?: 'teal' | 'orange' | 'red' | 'muted'; className?: string };

export function Badge({ children, tone = 'teal', className = '' }: BadgeProps) {
  return <span className={`badge badge-${tone} ${className}`}>{children}</span>;
}
