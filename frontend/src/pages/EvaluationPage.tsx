import { AlertTriangle, Beaker, CheckCircle2, Tags, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../App";
import { EmptyState } from "../components/Shared";
import { duration, humanize, percent, score } from "../format";
import type { Evaluation, Overall, RegressionResult } from "../types";

const PARTITIONS = [
  { id: "all", label: "All documents" },
  { id: "dev", label: "Development" },
  { id: "test", label: "Held-out test" },
  { id: "unassigned", label: "Unassigned" },
];

const OUTCOME_LABEL: Record<Overall, string> = { pass: "Source-verified", warn: "Needs attention", abstain: "Abstained" };

export default function EvaluationPage() {
  const { notify } = useApp();
  const [partition, setPartition] = useState("all");
  const [data, setData] = useState<Evaluation | null>(null);
  const [regression, setRegression] = useState<RegressionResult | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let active = true;
    api.evaluation(partition).then((result) => active && setData(result), (error: Error) => notify(error.message, "error"));
    return () => {
      active = false;
    };
  }, [partition, notify]);

  const runRegression = async () => {
    setRunning(true);
    try {
      setRegression(await api.regression());
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setRunning(false);
    }
  };

  const detection = data?.detection;
  const review = data?.review;
  const maxEdits = review ? Math.max(1, ...Object.values(review.field_edits)) : 1;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Evaluation</h1>
          <p>Every number comes from labels and decisions stored in this workspace. Nothing is estimated or pre-filled.</p>
        </div>
        <div className="chips">
          {PARTITIONS.map((p) => (
            <button key={p.id} className={partition === p.id ? "chip active" : "chip"} onClick={() => setPartition(p.id)}>{p.label}</button>
          ))}
        </div>
      </header>

      {data && data.synthetic_documents > 0 && (
        <div className="notice">
          <AlertTriangle size={15} />
          <span>{data.synthetic_documents} of {data.documents} documents here are synthetic. Do not report these scores as research results.</span>
        </div>
      )}

      <section className="section">
        <h2>Requirement detection</h2>
        {detection && detection.labeled === 0 ? (
          <EmptyState icon={<Tags size={22} />} title="No labeled passages in this view">
            <p>Open a document, choose Label passages, and mark what is and is not a requirement. Scores appear here as soon as labels exist.</p>
            <Link className="btn" to="/documents">Go to documents</Link>
          </EmptyState>
        ) : detection && (
          <>
            <div className="tiles">
              <Tile label="F1 (requirement class)" value={score(detection.f1)} sub={detection.f1_ci95 ? `95% CI ${score(detection.f1_ci95[0])}–${score(detection.f1_ci95[1])}` : "Interval needs 2+ documents"} primary />
              <Tile label="Precision" value={score(detection.precision)} sub={`${detection.confusion.tp} of ${detection.confusion.tp + detection.confusion.fp} detected`} />
              <Tile label="Recall" value={score(detection.recall)} sub={`${detection.confusion.tp} of ${detection.confusion.tp + detection.confusion.fn} labeled`} />
              <Tile label="Macro-F1" value={score(detection.macro_f1)} sub={`${detection.labeled} passages${detection.uncertain_excluded ? `, ${detection.uncertain_excluded} uncertain excluded` : ""}`} />
            </div>

            <div className="two-col">
              <div>
                <h3>Confusion matrix</h3>
                <table className="matrix">
                  <thead>
                    <tr><th /><th>Detected</th><th>Not detected</th></tr>
                  </thead>
                  <tbody>
                    <tr><th>Requirement</th><td className="good">{detection.confusion.tp}<small>true positive</small></td><td className="bad">{detection.confusion.fn}<small>missed</small></td></tr>
                    <tr><th>Not a requirement</th><td className="bad">{detection.confusion.fp}<small>false alarm</small></td><td className="good">{detection.confusion.tn}<small>true negative</small></td></tr>
                  </tbody>
                </table>
              </div>
              <div>
                <h3>By document</h3>
                <table className="table">
                  <thead><tr><th>Document</th><th className="num">Labeled</th><th className="num">Precision</th><th className="num">Recall</th><th className="num">F1</th></tr></thead>
                  <tbody>
                    {detection.documents.map((row) => (
                      <tr key={row.document_id}>
                        <td><Link to={`/documents/${row.document_id}`}>{row.filename}</Link></td>
                        <td className="num">{row.labeled}</td><td className="num">{score(row.precision)}</td><td className="num">{score(row.recall)}</td><td className="num">{score(row.f1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {detection.errors.length > 0 && (
              <details className="disclosure errors" open={detection.errors.length <= 8}>
                <summary>Error examples ({detection.errors.length})</summary>
                <ul className="error-list">
                  {detection.errors.map((error) => (
                    <li key={error.span_id}>
                      <span className={`err-kind ${error.kind}`}>{error.kind === "fp" ? "False alarm" : "Missed"}</span>
                      <p>{error.text}</p>
                      <small>{error.filename}{error.page ? `, page ${error.page}` : ""} · {error.reason}</small>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>

      {review && (
        <section className="section">
          <h2>Expert review</h2>
          {review.reviewed === 0 ? (
            <p className="muted">No records in this view have been reviewed yet. {review.total_records} are waiting.</p>
          ) : (
            <>
              <div className="tiles">
                <Tile label="Accepted unchanged" value={percent(review.accepted_unchanged_rate)} sub={`${review.status.accepted} of ${review.reviewed} reviewed`} />
                <Tile label="Kept after review" value={percent(review.kept_rate)} sub={`${review.status.edited} corrected, ${review.status.rejected} rejected`} />
                <Tile label="Median time per kept record" value={duration(review.median_ms_per_kept_record)} sub="Measured in the review screen" />
                <Tile label="Remaining" value={String(review.status.unreviewed)} sub={`of ${review.total_records} records`} />
              </div>
              <div className="two-col">
                <div>
                  <h3>Reviewer decision by validator outcome</h3>
                  <table className="table">
                    <thead><tr><th>Validator</th><th className="num">Accepted</th><th className="num">Corrected</th><th className="num">Rejected</th><th className="num">Open</th></tr></thead>
                    <tbody>
                      {(Object.keys(OUTCOME_LABEL) as Overall[]).map((key) => {
                        const row = review.validator_outcomes[key];
                        return <tr key={key}><td>{OUTCOME_LABEL[key]}</td><td className="num">{row.accepted}</td><td className="num">{row.edited}</td><td className="num">{row.rejected}</td><td className="num">{row.unreviewed}</td></tr>;
                      })}
                    </tbody>
                  </table>
                </div>
                <div>
                  <h3>Corrections by field</h3>
                  <ul className="hbars">
                    {Object.entries(review.field_edits).map(([field, count]) => (
                      <li key={field}>
                        <span>{humanize(field)}</span>
                        <span className="hbar"><i style={{ width: `${(count / maxEdits) * 100}%` }} /></span>
                        <span className="num">{count}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          )}
        </section>
      )}

      <section className="section">
        <div className="section-head">
          <div>
            <h2>Rule regression check</h2>
            <p className="muted">Synthetic sentences written alongside the rules. This confirms the software still behaves as designed. It says nothing about real-world accuracy.</p>
          </div>
          <button className="btn" disabled={running} onClick={() => void runRegression()}>
            <Beaker size={14} /> {running ? "Running…" : "Run check"}
          </button>
        </div>
        {regression && (
          <div className="regression">
            <span className={regression.failures.length ? "reg-status fail" : "reg-status ok"}>
              {regression.failures.length ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
              {regression.cases - regression.failures.length} of {regression.cases} cases behave as expected
            </span>
            <ul>
              {regression.failures.map((failure) => <li key={failure.text}>{failure.text}</li>)}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

function Tile({ label, value, sub, primary }: { label: string; value: string; sub: string; primary?: boolean }) {
  return (
    <div className={`tile${primary ? " tile-primary" : ""}`}>
      <span className="tile-label">{label}</span>
      <span className="tile-value">{value}</span>
      <span className="tile-sub">{sub}</span>
    </div>
  );
}
