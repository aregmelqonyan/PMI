import { Check, ChevronDown, MapPin, Pencil, Plus, RotateCcw, Trash2, Undo2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type RecordEdits } from "../api";
import { useApp } from "../App";
import { dateTime, duration, humanize, unitSymbol } from "../format";
import type { Constraint, HistoryEvent, Meta, Operator, RecordItem, RequirementType } from "../types";
import { Checks, ConstraintLine, Field, OverallBadge, Quote, ReviewBadge } from "./Shared";

const TYPES: RequirementType[] = ["functional", "performance", "interface", "safety", "environmental", "other"];
const OPERATORS: Operator[] = ["<=", "<", ">=", ">", "="];

interface Props {
  item: RecordItem;
  meta: Meta | null;
  editing: boolean;
  onEditing: (editing: boolean) => void;
  onLocate: () => void;
  onDecide: (decision: "accepted" | "rejected" | "unreviewed") => void;
  onSave: (edits: RecordEdits) => Promise<void>;
  onRestore: () => void;
}

export default function RecordDetail({ item, meta, editing, onEditing, onLocate, onDecide, onSave, onRestore }: Props) {
  const { record, validation, review_status: status } = item;
  const failed = validation.overall === "abstain";
  const reviewed = status !== "unreviewed";

  return (
    <section className="detail" aria-label="Requirement record">
      <header className="detail-head">
        <div className="detail-id">
          <code>{record.requirement_id}</code>
          {record.source_label && <span className="source-label">{record.source_label}</span>}
        </div>
        <div className="detail-badges">
          <OverallBadge overall={validation.overall} />
          <ReviewBadge status={status} />
        </div>
      </header>

      <div className="detail-body">
        {editing ? (
          <EditForm item={item} meta={meta} onCancel={() => onEditing(false)} onSave={onSave} onRestore={onRestore} />
        ) : (
          <>
            <div className="block">
              <div className="block-title">
                <span>Source evidence</span>
                {record.evidence.page && (
                  <button className="link" onClick={onLocate}>
                    <MapPin size={13} /> Page {record.evidence.page}
                  </button>
                )}
              </div>
              <Quote evidence={record.evidence} constraints={record.constraints} />
              <div className="meta-line">
                {record.evidence.section && <span>§ {record.evidence.section}</span>}
                <span>
                  chars {record.evidence.start_char}–{record.evidence.end_char} of {record.evidence.block_id}
                </span>
              </div>
            </div>

            {record.constraints.length > 0 && (
              <div className="block">
                <div className="block-title">
                  <span>Constraints</span>
                </div>
                <div className="constraints">
                  {record.constraints.map((constraint, index) => (
                    <ConstraintLine key={index} constraint={constraint} />
                  ))}
                </div>
              </div>
            )}

            <div className="block">
              <div className="block-title">
                <span>Extracted fields</span>
              </div>
              <dl className="fields">
                <Field label="Component" empty={!record.component}>{record.component}</Field>
                <Field label={record.negated && record.constraints.length === 0 ? "Prohibited action" : "Action or state"} empty={!record.action_or_state}>
                  {record.action_or_state}
                </Field>
                <Field label="Condition" empty={!record.condition}>{record.condition}</Field>
                <Field label="Exception" empty={!record.exception}>{record.exception}</Field>
                <Field label="Type">{humanize(record.requirement_type)}</Field>
                <Field label="Modality">{humanize(record.modality)}</Field>
              </dl>
            </div>

            <div className="block">
              <div className="block-title">
                <span>Deterministic checks</span>
              </div>
              <Checks checks={validation.checks} />
              <p className="fineprint">These checks show the record is consistent with the source text. Engineering correctness is the reviewer's decision.</p>
            </div>

            <Disclosure title="Why the rules produced this">
              <ul className="trace">
                {record.trace.map((entry, index) => (
                  <li key={index}>
                    <code>{entry}</code>
                  </li>
                ))}
              </ul>
              <p className="fineprint">{record.method}</p>
            </Disclosure>
            <Disclosure title="Structured JSON">
              <pre className="json">{JSON.stringify(stripRects(record), null, 2)}</pre>
            </Disclosure>
            <HistoryPanel recordId={item.id} version={`${item.updated_at}-${status}`} />
          </>
        )}
      </div>

      {!editing && (
        <footer className="actions">
          {failed && !reviewed && <p className="override-note">A check failed. Accepting records an expert override.</p>}
          <div className="action-row">
            {reviewed ? (
              <button className="btn" onClick={() => onDecide("unreviewed")}>
                <Undo2 size={15} /> Reopen
              </button>
            ) : (
              <button className="btn btn-danger" onClick={() => onDecide("rejected")}>
                <X size={15} /> Reject <kbd>R</kbd>
              </button>
            )}
            <button className="btn" onClick={() => onEditing(true)}>
              <Pencil size={14} /> Correct <kbd>E</kbd>
            </button>
            <button className="btn btn-primary" disabled={status === "accepted" || status === "edited"} onClick={() => onDecide("accepted")}>
              <Check size={15} /> {failed ? "Accept anyway" : "Accept"} <kbd>A</kbd>
            </button>
          </div>
        </footer>
      )}
    </section>
  );
}

function stripRects(record: RecordItem["record"]) {
  const { rects: _rects, ...evidence } = record.evidence;
  return { ...record, evidence };
}

function Disclosure({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className="disclosure">
      <summary>
        <ChevronDown size={15} /> {title}
      </summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}

const ACTION_TEXT: Record<string, string> = {
  edit: "Corrected fields",
  accepted: "Accepted",
  accepted_with_override: "Accepted despite a failed check",
  rejected: "Rejected",
  unreviewed: "Reopened",
  reopened: "Reopened",
  restore_original: "Restored original output",
};

function HistoryPanel({ recordId, version }: { recordId: string; version: string }) {
  const [events, setEvents] = useState<HistoryEvent[] | null>(null);
  useEffect(() => {
    let active = true;
    api.history(recordId).then((rows) => active && setEvents(rows), () => active && setEvents([]));
    return () => {
      active = false;
    };
  }, [recordId, version]);

  return (
    <Disclosure title={`Audit trail${events?.length ? ` (${events.length})` : ""}`}>
      {events && events.length === 0 && <p className="fineprint">No human action yet. The original output is preserved.</p>}
      <ol className="history">
        {events?.map((event) => (
          <li key={event.id}>
            <strong>{ACTION_TEXT[event.action] ?? humanize(event.action)}</strong>
            <span>
              {event.actor} · {dateTime(event.at)}
              {event.elapsed_ms > 0 && ` · ${duration(event.elapsed_ms)}`}
            </span>
          </li>
        ))}
      </ol>
    </Disclosure>
  );
}

const nullable = (value: string) => (value.trim() === "" ? null : value);

function EditForm({ item, meta, onCancel, onSave, onRestore }: { item: RecordItem; meta: Meta | null; onCancel: () => void; onSave: (edits: RecordEdits) => Promise<void>; onRestore: () => void }) {
  const { notify } = useApp();
  const { record } = item;
  const [component, setComponent] = useState(record.component ?? "");
  const [action, setAction] = useState(record.action_or_state ?? "");
  const [condition, setCondition] = useState(record.condition ?? "");
  const [exception, setException] = useState(record.exception ?? "");
  const [type, setType] = useState<RequirementType>(record.requirement_type);
  const [constraints, setConstraints] = useState<Constraint[]>(record.constraints.map((c) => ({ ...c })));
  const [saving, setSaving] = useState(false);

  const update = (index: number, patch: Partial<Constraint>) => setConstraints((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const submit = async () => {
    if (constraints.some((c) => !c.surface_text.trim())) {
      notify("Each constraint needs the exact words it comes from.", "error");
      return;
    }
    setSaving(true);
    try {
      await onSave({ component: nullable(component), action_or_state: nullable(action), condition: nullable(condition), exception: nullable(exception), requirement_type: type, constraints });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="edit"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <Quote evidence={record.evidence} constraints={record.constraints} />
      <label>Component<input value={component} onChange={(e) => setComponent(e.target.value)} /></label>
      <label>Action or state<input value={action} onChange={(e) => setAction(e.target.value)} /></label>
      <label>Condition<input value={condition} onChange={(e) => setCondition(e.target.value)} /></label>
      <label>Exception<input value={exception} onChange={(e) => setException(e.target.value)} /></label>
      <label>
        Requirement type
        <select value={type} onChange={(e) => setType(e.target.value as RequirementType)}>
          {TYPES.map((value) => <option key={value} value={value}>{humanize(value)}</option>)}
        </select>
      </label>

      <div className="edit-constraints">
        <div className="block-title"><span>Constraints</span></div>
        {constraints.map((constraint, index) => (
          <fieldset key={index}>
            <div className="edit-row">
              <label>Operator
                <select value={constraint.operator ?? ""} onChange={(e) => update(index, { operator: (e.target.value || null) as Operator | null })}>
                  <option value="">Not stated</option>
                  {OPERATORS.map((op) => <option key={op} value={op}>{op}</option>)}
                </select>
              </label>
              <label>Value
                <input type="number" step="any" value={constraint.value ?? ""} onChange={(e) => update(index, { value: e.target.value === "" ? null : Number(e.target.value) })} />
              </label>
              <label>Unit
                <select value={constraint.unit ?? ""} onChange={(e) => update(index, { unit: e.target.value || null })}>
                  <option value="">None</option>
                  {[...new Set([...(constraint.unit ? [constraint.unit] : []), ...(meta?.units ?? [])])].map((unit) => (
                    <option key={unit} value={unit}>{unitSymbol(unit)}</option>
                  ))}
                </select>
              </label>
              <button type="button" className="icon-btn" aria-label={`Remove constraint ${index + 1}`} onClick={() => setConstraints((rows) => rows.filter((_, i) => i !== index))}>
                <Trash2 size={15} />
              </button>
            </div>
            <label>Parameter<input value={constraint.parameter ?? ""} onChange={(e) => update(index, { parameter: nullable(e.target.value) })} /></label>
            <label>Exact source words
              <input
                value={constraint.surface_text}
                readOnly={constraint.start_char !== null}
                onChange={(e) => update(index, { surface_text: e.target.value })}
                placeholder="Copy the words from the quote above"
              />
            </label>
          </fieldset>
        ))}
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => setConstraints((rows) => [...rows, { parameter: null, operator: null, value: null, tolerance: null, unit: null, condition: nullable(condition), surface_text: "", start_char: null, end_char: null }])}
        >
          <Plus size={14} /> Add constraint
        </button>
      </div>

      <p className="fineprint">Checks run again on save. A value that contradicts the quoted words is flagged, and the original output stays in the audit trail.</p>
      <div className="action-row">
        <button type="button" className="btn btn-quiet" onClick={onRestore}><RotateCcw size={14} /> Restore original</button>
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : "Save correction"}</button>
      </div>
    </form>
  );
}
