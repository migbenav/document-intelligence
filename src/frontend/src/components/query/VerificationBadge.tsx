import { useTranslation } from '@/i18n';
import { cn } from '@/lib/utils';

// --- Props ---

export interface VerificationBadgeProps {
  /** Whether the evidence is verified against the source document. */
  verified: boolean;
  /** Optional additional CSS classes. */
  className?: string;
}

// --- Icons ---

/**
 * Checkmark icon for verified status.
 * Uses aria-hidden since the text label conveys the meaning.
 */
function CheckIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="h-4 w-4 shrink-0"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/**
 * Warning triangle icon for unverified status.
 * Uses aria-hidden since the text label conveys the meaning.
 */
function WarningIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="h-4 w-4 shrink-0"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495ZM10 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 10 5Zm0 9a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

// --- Main Component ---

/**
 * VerificationBadge displays the verification status of evidence.
 *
 * Accessibility:
 * - Uses role="status" to announce state to screen readers
 * - Keyboard-focusable via tabIndex={0}
 * - Distinct iconography AND text labels (not color alone)
 * - WCAG 2.1 AA contrast: green-800 on green-100 (verified), amber-800 on amber-100 (unverified)
 */
export function VerificationBadge({ verified, className }: VerificationBadgeProps) {
  const { t } = useTranslation();

  const label = verified
    ? t('query.evidence.verified')
    : t('query.evidence.notVerified');

  return (
    <span
      role="status"
      tabIndex={0}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        verified
          ? 'bg-green-100 text-green-800'
          : 'bg-amber-100 text-amber-800',
        className,
      )}
      data-testid={verified ? 'verification-badge-verified' : 'verification-badge-unverified'}
    >
      {verified ? <CheckIcon /> : <WarningIcon />}
      <span>{label}</span>
    </span>
  );
}
