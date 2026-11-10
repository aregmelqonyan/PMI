import { AlertTriangle, CheckCircle2, CircleDashed, Hand, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { constraintValue, humanize, operatorSymbol } from "../format";
import type { Check, Constraint, Evidence, Overall, ReviewStatus } from "../types";

const OVERALL = {
  pass: { label: "Source-verified", icon: ShieldCheck },
  warn: { label: "Needs attention", icon: AlertTriangle },
  abstain: { label: "Abstained", icon: Hand },
} as const;

export function OverallBadge({ overall, compact }: { overall: Overall; compact?: boolean }) {
  const { label, icon: Icon } = OVERALL[overall];
  return (
    <span className={`badge badge-${overall}`} title={label}>
      <Icon size={13} />
      {!compact && label}
    </span>
  );
}

const REVIEW = {
  unreviewed: { label: "Unreviewed", icon: CircleDashed },
  accepted: { label: "Accepted", icon: CheckCircle2 },
  edited: { label: "Corrected", icon: CheckCircle2 },
  rejected: { label: "Rejected", icon: XCircle },
} as const;

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  const { label, icon: Icon } = REVIEW[status];
  return (
    <span className={`review review-${status}`}>
      <Icon size={13} />
      {label}
    </span>
  );
}

export function ConstraintLine({ constraint }: { constraint: Constraint }) {
  return (
    <div className="constraint">
      <div className="constraint-main">
        <span className="constraint-param">{constraint.parameter ? humanize(constraint.parameter) : "Quantity"}</span>
        <span className={`constraint-op${constraint.operator ? "" : " missing"}`}>{operatorSymbol(constraint.operator)}</span>
        <span className="constraint-value">{constraintValue(constraint)}</span>
      </div>
      <div className="constraint-surface">“{constraint.surface_text}”</div>
    </div>
  );
}

/** The quote with each constraint's exact characters marked, using the stored offsets. */
export function Quote({ evidence, constraints }: { evidence: Evidence; constraints: Constraint[] }) {
  const base = evidence.start_char;
  const text = evidence.quoted_text;
  const ranges = [
    ...new Map(
      constraints
        .filter((c) => c.start_char !== null && c.end_char !== null)
        .map((c) => [`${c.start_char}`, [c.start_char! - base, c.end_char! - base] as const]),
    ).values(),
  ].sort((a, b) => a[0] - b[0]);
  const parts: ReactNode[] = [];
  let cursor = 0;
  ranges.forEach(([start, end]) => {
    if (start < cursor || start < 0 || end > text.length) return;
    parts.push(text.slice(cursor, start));
    parts.push(<mark key={start}>{text.slice(start, end)}</mark>);
    cursor = end;
  });
  parts.push(text.slice(cursor));
  return <blockquote className="quote">{parts}</blockquote>;
}

const CHECK_ICON = { pass: CheckCircle2, warn: AlertTriangle, fail: ShieldAlert };

export function Checks({ checks }: { checks: Check[] }) {
  return (
    <ul className="checks">
      {checks.map((check) => {
        const Icon = CHECK_ICON[check.status];
        return (
          <li key={check.id} className={`check check-${check.status}`}>
            <Icon size={15} />
            <div>
              <strong>{check.label}</strong>
              <span>{check.detail}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function Field({ label, children, empty }: { label: string; children?: ReactNode; empty?: boolean }) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd className={empty ? "null" : undefined}>{empty ? "Not stated" : children}</dd>
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {children}
    </div>
  );
}
