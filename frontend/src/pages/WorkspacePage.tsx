import { AlertTriangle, ArrowLeft, Check, CircleHelp, Download, Inbox, Search, Tags, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, exportUrl, type RecordEdits } from "../api";
import { useApp } from "../App";
import PdfViewer, { type Highlight } from "../components/PdfViewer";
import RecordDetail from "../components/RecordDetail";
import { EmptyState, OverallBadge, ReviewBadge } from "../components/Shared";
import { constraintValue, operatorSymbol } from "../format";
import type { DocumentItem, GoldLabel, Meta, Partition, Passage, RecordItem } from "../types";

type Filter = "all" | "todo" | "attention" | "approved" | "rejected";
type PassageFilter = "all" | "detected" | "missed" | "unlabeled";

const FILTERS: { id: Filter; label: string; test: (r: RecordItem) => boolean }[] = [
  { id: "all", label: "All", test: () => true },
  { id: "todo", label: "To review", test: (r) => r.review_status === "unreviewed" },
  { id: "attention", label: "Attention", test: (r) => r.validation.overall !== "pass" && r.review_status === "unreviewed" },
  { id: "approved", label: "Approved", test: (r) => r.review_status === "accepted" || r.review_status === "edited" },
  { id: "rejected", label: "Rejected", test: (r) => r.review_status === "rejected" },
];

const MAX_ELAPSED_MS = 10 * 60 * 1000;

export default function WorkspacePage() {
  const { id = "" } = useParams();
  const { reviewer, notify } = useApp();
  const [document, setDocument] = useState<DocumentItem | null>(null);
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [passages, setPassages] = useState<Passage[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [tab, setTab] = useState<"records" | "passages">("records");
  const [filter, setFilter] = useState<Filter>("todo");
  const [passageFilter, setPassageFilter] = useState<PassageFilter>("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState(false);
  const [focusToken, setFocusToken] = useState(0);
  const openedAt = useRef(Date.now());

  useEffect(() => {
    let active = true;
    Promise.all([api.document(id), api.records(id), api.passages(id), api.meta()]).then(
      ([doc, rows, spans, info]) => {
        if (!active) return;
        setDocument(doc);
        setRecords(rows);
        setPassages(spans);
        setMeta(info);
        const first = rows.find((r) => r.review_status === "unreviewed") ?? rows[0];
        if (!rows.some((r) => r.review_status === "unreviewed")) setFilter("all");
        if (first) {
          setSelectedId(first.id);
          setPage(first.record.evidence.page ?? 1);
        }
      },
      (error: Error) => active && setFailed(error.message),
    );
    return () => {
      active = false;
    };
  }, [id]);

  useEffect(() => {
    openedAt.current = Date.now();
  }, [selectedId]);

  const elapsed = () => Math.min(Date.now() - openedAt.current, MAX_ELAPSED_MS);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const test = FILTERS.find((f) => f.id === filter)!.test;
    return records.filter((r) => test(r) && (!needle || r.record.evidence.quoted_text.toLowerCase().includes(needle) || (r.record.source_label ?? "").toLowerCase().includes(needle)));
  }, [records, filter, query]);

  const visiblePassages = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return passages.filter((p) => {
      if (needle && !p.text.toLowerCase().includes(needle)) return false;
      if (passageFilter === "detected") return p.detected;
      if (passageFilter === "missed") return !p.detected;
      if (passageFilter === "unlabeled") return p.gold_label === null;
      return true;
    });
  }, [passages, passageFilter, query]);

  const selected = records.find((r) => r.id === selectedId) ?? null;

  const select = useCallback(
    (record: RecordItem) => {
      setSelectedId(record.id);
      setEditing(false);
      if (record.record.evidence.page) setPage(record.record.evidence.page);
      setFocusToken((n) => n + 1);
    },
    [],
  );

  const replace = useCallback((next: RecordItem) => setRecords((rows) => rows.map((r) => (r.id === next.id ? next : r))), []);

  const decide = useCallback(
    async (decision: "accepted" | "rejected" | "unreviewed") => {
      if (!selected) return;
      try {
        const updated = await api.decide(selected.id, decision, reviewer, elapsed());
        const index = visible.findIndex((r) => r.id === updated.id);
        const following = decision === "unreviewed" ? null : visible[index + 1] ?? visible[index - 1] ?? null;
        replace(updated);
        if (following && following.id !== updated.id) select(following);
        else openedAt.current = Date.now();
      } catch (error) {
        notify((error as Error).message, "error");
      }
    },
    [selected, reviewer, visible, replace, select, notify],
  );

  const save = async (edits: RecordEdits) => {
    if (!selected) return;
    try {
      const updated = await api.edit(selected.id, edits, reviewer, elapsed());
      replace(updated);
      setEditing(false);
      openedAt.current = Date.now();
      notify(updated.validation.overall === "abstain" ? "Saved but not approved: a check fails against the source." : "Correction saved and checked against the source.", updated.validation.overall === "abstain" ? "error" : "info");
    } catch (error) {
      notify((error as Error).message, "error");
    }
  };

  const restore = async () => {
    if (!selected) return;
    try {
      replace(await api.restore(selected.id, reviewer));
      setEditing(false);
      notify("Original extraction restored.");
    } catch (error) {
      notify((error as Error).message, "error");
    }
  };

  const label = async (passage: Passage, value: GoldLabel) => {
    const next = passage.gold_label === value ? null : value;
    try {
      const updated = await api.label(passage.span_id, next, reviewer);
      setPassages((rows) => rows.map((p) => (p.span_id === updated.span_id ? updated : p)));
    } catch (error) {
      notify((error as Error).message, "error");
    }
  };

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (editing || tab !== "records" || event.metaKey || event.ctrlKey || event.altKey) return;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      const index = visible.findIndex((r) => r.id === selectedId);
      if (event.key === "j" || event.key === "ArrowDown") {
        const next = visible[index + 1];
        if (next) {
          event.preventDefault();
          select(next);
        }
      } else if (event.key === "k" || event.key === "ArrowUp") {
        const previous = visible[index - 1];
        if (previous) {
          event.preventDefault();
          select(previous);
        }
      } else if (event.key === "a" && selected && selected.review_status !== "accepted" && selected.review_status !== "edited") {
        void decide("accepted");
      } else if (event.key === "r" && selected && selected.review_status === "unreviewed") {
        void decide("rejected");
      } else if (event.key === "e" && selected) {
        setEditing(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [editing, tab, visible, selectedId, selected, select, decide]);

  const highlights: Highlight[] = useMemo(() => {
    if (tab === "passages") {
      return passages
        .filter((p) => p.page === page)
        .map((p) => ({ key: p.span_id, rects: p.rects, tone: p.detected ? "pass" : "muted", label: p.text.slice(0, 120) }));
    }
    return records
      .filter((r) => r.record.evidence.page === page)
      .map((r) => ({
        key: r.id,
        rects: r.record.evidence.rects,
        tone: r.review_status === "rejected" ? "rejected" : r.validation.overall,
        label: r.record.evidence.quoted_text.slice(0, 120),
      }));
  }, [tab, passages, records, page]);

  const partition = async (value: Partition) => {
    try {
      setDocument(await api.setPartition(id, value));
    } catch (error) {
      notify((error as Error).message, "error");
    }
  };

  if (failed) {
    return (
      <div className="page">
        <EmptyState icon={<AlertTriangle size={22} />} title="This document could not be opened">
          <p>{failed}</p>
          <Link className="btn" to="/documents">Back to documents</Link>
        </EmptyState>
      </div>
    );
  }
  if (!document) return <div className="page-loading">Opening document…</div>;

  const reviewed = records.filter((r) => r.review_status !== "unreviewed").length;
  const approved = records.filter((r) => r.review_status === "accepted" || r.review_status === "edited").length;
  const labeled = passages.filter((p) => p.gold_label).length;

  return (
    <div className="workspace">
      <header className="ws-head">
        <Link to="/documents" className="icon-btn" aria-label="Back to documents"><ArrowLeft size={16} /></Link>
        <div className="ws-title">
          <h1>{document.filename}</h1>
          <span>{document.synthetic ? "Synthetic document · " : ""}{document.method}</span>
        </div>
        <div className="ws-progress">
          <span>{reviewed} of {records.length} reviewed</span>
          <span className="bar"><i style={{ width: `${records.length ? (reviewed / records.length) * 100 : 0}%` }} /></span>
        </div>
        <label className="ws-select">
          <span>Split</span>
          <select value={document.partition} onChange={(event) => void partition(event.target.value as Partition)}>
            <option value="unassigned">Unassigned</option>
            <option value="dev">Development</option>
            <option value="test">Held-out test</option>
          </select>
        </label>
        <details className="menu">
          <summary className="btn"><Download size={14} /> Export</summary>
          <div className="menu-pop">
            <a href={exportUrl(id, "jsonl", "approved")} className={approved ? "" : "disabled"}>Approved records · JSONL <small>{approved}</small></a>
            <a href={exportUrl(id, "csv", "approved")} className={approved ? "" : "disabled"}>Approved records · CSV <small>{approved}</small></a>
            <a href={exportUrl(id, "jsonl", "all")}>All records · JSONL <small>{records.length}</small></a>
            <a href={exportUrl(id, "csv", "all")}>All records · CSV <small>{records.length}</small></a>
          </div>
        </details>
      </header>

      {document.warnings.length > 0 && (
        <div className="ws-warnings">
          <AlertTriangle size={14} />
          <span>{document.warnings.join(" ")}</span>
        </div>
      )}

      <div className="ws-grid">
        <PdfViewer
          documentId={id}
          pages={document.pages}
          page={page}
          onPage={setPage}
          highlights={highlights}
          selectedKey={tab === "records" ? selectedId : selectedSpan}
          focusToken={focusToken}
          legend={tab === "records" ? "validation" : "detection"}
          onSelect={(key) => {
            if (tab === "passages") setSelectedSpan(key);
            else {
              const record = records.find((r) => r.id === key);
              if (record) select(record);
            }
          }}
        />

        <section className="queue" aria-label={tab === "records" ? "Requirement records" : "Passages"}>
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={tab === "records"} className={tab === "records" ? "active" : ""} onClick={() => setTab("records")}>
              <Inbox size={14} /> Records <small>{records.length}</small>
            </button>
            <button role="tab" aria-selected={tab === "passages"} className={tab === "passages" ? "active" : ""} onClick={() => setTab("passages")}>
              <Tags size={14} /> Label passages <small>{labeled}/{passages.length}</small>
            </button>
          </div>
          <div className="queue-tools">
            <div className="search">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search text or ID" aria-label="Search" />
            </div>
            {tab === "records" ? (
              <div className="chips">
                {FILTERS.map((f) => (
                  <button key={f.id} className={filter === f.id ? "chip active" : "chip"} onClick={() => setFilter(f.id)}>
                    {f.label} <small>{records.filter(f.test).length}</small>
                  </button>
                ))}
              </div>
            ) : (
              <div className="chips">
                {(["all", "detected", "missed", "unlabeled"] as PassageFilter[]).map((f) => (
                  <button key={f} className={passageFilter === f ? "chip active" : "chip"} onClick={() => setPassageFilter(f)}>
                    {f === "missed" ? "Not detected" : f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
            )}
          </div>

          {tab === "records" ? (
            <ul className="queue-list">
              {visible.map((item) => {
                const first = item.record.constraints[0];
                return (
                  <li key={item.id}>
                    <button className={`queue-item${item.id === selectedId ? " active" : ""}`} onClick={() => select(item)}>
                      <span className="queue-top">
                        <OverallBadge overall={item.validation.overall} compact />
                        <span className="queue-comp">{item.record.component ?? item.record.action_or_state ?? "No subject found"}</span>
                        {item.record.evidence.page && <small>p.{item.record.evidence.page}</small>}
                      </span>
                      <span className="queue-text">{item.record.evidence.quoted_text}</span>
                      <span className="queue-bottom">
                        {first ? (
                          <code>{operatorSymbol(first.operator)} {constraintValue(first)}{item.record.constraints.length > 1 ? ` +${item.record.constraints.length - 1}` : ""}</code>
                        ) : <span />}
                        {item.review_status !== "unreviewed" && <ReviewBadge status={item.review_status} />}
                      </span>
                    </button>
                  </li>
                );
              })}
              {visible.length === 0 && (
                <li className="queue-empty">
                  {records.length === 0 ? "No requirements were detected in this document." : filter === "todo" ? "Nothing left to review here." : "No records match this view."}
                </li>
              )}
            </ul>
          ) : (
            <ul className="queue-list">
              {visiblePassages.slice(0, 400).map((passage) => (
                <li key={passage.span_id}>
                  <div
                    className={`passage${passage.span_id === selectedSpan ? " active" : ""}`}
                    onClick={() => {
                      setSelectedSpan(passage.span_id);
                      if (passage.page) setPage(passage.page);
                      setFocusToken((n) => n + 1);
                    }}
                  >
                    <p>{passage.text}</p>
                    <div className="passage-foot">
                      <span className={passage.detected ? "det yes" : "det"}>{passage.detected ? "Detected" : "Not detected"} · {passage.reason}</span>
                      <div className="label-group" role="group" aria-label="Gold label">
                        <LabelButton passage={passage} value="requirement" onLabel={label} title="Requirement"><Check size={13} /></LabelButton>
                        <LabelButton passage={passage} value="non_requirement" onLabel={label} title="Not a requirement"><X size={13} /></LabelButton>
                        <LabelButton passage={passage} value="uncertain" onLabel={label} title="Uncertain"><CircleHelp size={13} /></LabelButton>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
              {visiblePassages.length > 400 && <li className="queue-empty">Showing the first 400. Use search or a filter to narrow the list.</li>}
              {visiblePassages.length === 0 && <li className="queue-empty">No passages match this view.</li>}
            </ul>
          )}
        </section>

        {tab === "records" && selected ? (
          <RecordDetail
            item={selected}
            meta={meta}
            editing={editing}
            onEditing={setEditing}
            onLocate={() => {
              setPage(selected.record.evidence.page ?? 1);
              setFocusToken((n) => n + 1);
            }}
            onDecide={(decision) => void decide(decision)}
            onSave={save}
            onRestore={() => void restore()}
          />
        ) : (
          <section className="detail detail-help">
            {tab === "passages" ? (
              <EmptyState icon={<Tags size={22} />} title="Build the gold sample">
                <p>Label each passage independently of what the rules detected. These labels produce the measured precision, recall and F1 on the Evaluation page.</p>
                <ul className="help-list">
                  <li><Check size={13} /> Requirement</li>
                  <li><X size={13} /> Not a requirement</li>
                  <li><CircleHelp size={13} /> Uncertain, excluded from scores</li>
                </ul>
              </EmptyState>
            ) : (
              <EmptyState icon={<Inbox size={22} />} title="No record selected" />
            )}
          </section>
        )}
      </div>
    </div>
  );
}

function LabelButton({ passage, value, onLabel, title, children }: { passage: Passage; value: GoldLabel; onLabel: (p: Passage, v: GoldLabel) => void; title: string; children: React.ReactNode }) {
  const active = passage.gold_label === value;
  return (
    <button
      className={`label-btn${active ? ` on-${value}` : ""}`}
      title={title}
      aria-label={title}
      aria-pressed={active}
      onClick={(event) => {
        event.stopPropagation();
        onLabel(passage, value);
      }}
    >
      {children}
    </button>
  );
}
