import { Play } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useApp } from "../App";
import { Checks, ConstraintLine, Field, OverallBadge, Quote } from "../components/Shared";
import { humanize } from "../format";
import type { PlaygroundResult } from "../types";

const EXAMPLES = [
  { label: "Negated limit", text: "During continuous discharge, the battery-case temperature shall not exceed 60 degrees Celsius." },
  { label: "Two obligations", text: "The relay shall open within 50 ms, and the indicator shall illuminate within 2 s." },
  { label: "Range", text: "The unit shall operate between -40 °C and 85 °C." },
  { label: "Not binding", text: "The battery subsystem should be lightweight." },
  { label: "Implicit limit", text: "Maximum allowable load: 150 N" },
  { label: "Unresolved value", text: "The heater power shall be TBD W during lunar night." },
];

export default function PlaygroundPage() {
  const { notify } = useApp();
  const [text, setText] = useState(EXAMPLES[0].text);
  const [result, setResult] = useState<PlaygroundResult | null>(null);
  const [running, setRunning] = useState(false);

  const run = useCallback(
    async (value: string) => {
      if (!value.trim()) return;
      setRunning(true);
      try {
        setResult(await api.playground(value));
      } catch (error) {
        notify((error as Error).message, "error");
      } finally {
        setRunning(false);
      }
    },
    [notify],
  );

  useEffect(() => {
    void run(EXAMPLES[0].text);
  }, [run]);

  const nonRequirements = result?.passages.filter((p) => !p.detected) ?? [];

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <div>
          <h1>Try a sentence</h1>
          <p>See how the B0 rules and the source checks treat any wording. Nothing here is saved.</p>
        </div>
      </header>

      <div className="play-input">
        <textarea
          aria-label="Requirement text"
          rows={3}
          maxLength={5000}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) void run(text);
          }}
        />
        <div className="play-bar">
          <div className="chips">
            {EXAMPLES.map((example) => (
              <button
                key={example.label}
                className={text === example.text ? "chip active" : "chip"}
                onClick={() => {
                  setText(example.text);
                  void run(example.text);
                }}
              >
                {example.label}
              </button>
            ))}
          </div>
          <button className="btn btn-primary" disabled={running || !text.trim()} onClick={() => void run(text)}>
            <Play size={14} /> Extract
          </button>
        </div>
      </div>

      {result?.records.map(({ record, validation }) => (
        <article className="card" key={record.requirement_id}>
          <div className="card-head">
            <h2>{record.component ?? record.action_or_state ?? "Requirement"}</h2>
            <OverallBadge overall={validation.overall} />
          </div>
          <Quote evidence={record.evidence} constraints={record.constraints} />
          {record.constraints.length > 0 && (
            <div className="constraints">
              {record.constraints.map((constraint, index) => <ConstraintLine key={index} constraint={constraint} />)}
            </div>
          )}
          <div className="play-columns">
            <dl className="fields">
              <Field label="Component" empty={!record.component}>{record.component}</Field>
              <Field label={record.negated && record.constraints.length === 0 ? "Prohibited action" : "Action or state"} empty={!record.action_or_state}>{record.action_or_state}</Field>
              <Field label="Condition" empty={!record.condition}>{record.condition}</Field>
              <Field label="Type">{humanize(record.requirement_type)}</Field>
            </dl>
            <Checks checks={validation.checks} />
          </div>
        </article>
      ))}

      {nonRequirements.map((passage) => (
        <article className="card card-muted" key={passage.span_id}>
          <div className="card-head">
            <h2>No record created</h2>
            <span className="tag">{humanize(passage.modality)}</span>
          </div>
          <blockquote className="quote">{passage.text}</blockquote>
          <p className="fineprint">{passage.reason}.</p>
        </article>
      ))}
    </div>
  );
}
