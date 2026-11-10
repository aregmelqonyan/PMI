import { ArrowRight, FileText, Sparkles, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../App";
import { EmptyState } from "../components/Shared";
import type { DocumentItem } from "../types";

export default function DocumentsPage() {
  const { notify } = useApp();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<DocumentItem[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    api.documents().then(setDocuments, (error: Error) => {
      setDocuments([]);
      notify(error.message, "error");
    });
  }, [notify]);

  useEffect(refresh, [refresh]);

  const run = async (label: string, action: () => Promise<{ document: DocumentItem; duplicate: boolean }>) => {
    setBusy(label);
    try {
      const { document, duplicate } = await action();
      if (duplicate) notify("This exact file is already in the corpus, so it was not added twice.");
      navigate(`/documents/${document.id}`);
    } catch (error) {
      notify((error as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };

  const upload = (file?: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      notify("Only PDF files are supported in this pilot.", "error");
      return;
    }
    void run(`Reading ${file.name}…`, () => api.upload(file));
  };

  const remove = async (document: DocumentItem) => {
    const reviewed = document.records.reviewed + document.passages.labeled;
    const detail = reviewed ? ` This also deletes ${reviewed} review decisions and labels.` : "";
    if (!window.confirm(`Delete “${document.filename}”?${detail}`)) return;
    try {
      await api.deleteDocument(document.id);
      refresh();
    } catch (error) {
      notify((error as Error).message, "error");
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Documents</h1>
          <p>Turn engineering PDFs into structured requirements, each one tied to the exact words it came from.</p>
        </div>
      </header>

      <div
        className={`dropzone${dragging ? " dragging" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          upload(event.dataTransfer.files[0]);
        }}
      >
        <UploadCloud size={26} />
        <div className="dropzone-text">
          <strong>{busy ?? "Drop a text-native PDF here"}</strong>
          <span>Processed on this computer. Scanned pages are reported, not guessed at.</span>
        </div>
        <div className="dropzone-actions">
          <button className="btn btn-primary" disabled={!!busy} onClick={() => input.current?.click()}>
            Choose PDF
          </button>
          <button className="btn" disabled={!!busy} onClick={() => void run("Building the sample…", api.sample)}>
            <Sparkles size={14} /> Load synthetic sample
          </button>
        </div>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          hidden
          onChange={(event) => {
            upload(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </div>

      {documents && documents.length === 0 && (
        <EmptyState icon={<FileText size={22} />} title="No documents yet">
          <p>Upload a PDF, or load the synthetic sample to see the full review flow.</p>
        </EmptyState>
      )}

      {documents && documents.length > 0 && (
        <div className="doc-list">
          {documents.map((document) => {
            const { total, reviewed } = document.records;
            const progress = total ? (reviewed / total) * 100 : 0;
            return (
              <div className="doc-row" key={document.id}>
                <Link className="doc-main" to={`/documents/${document.id}`}>
                  <span className="doc-icon"><FileText size={18} /></span>
                  <span className="doc-name">
                    <strong>{document.filename}</strong>
                    <small>
                      {document.pages.length} {document.pages.length === 1 ? "page" : "pages"} · {document.passages.total} passages · <code>{document.sha256.slice(0, 10)}</code>
                    </small>
                  </span>
                  <span className="doc-tags">
                    {document.synthetic && <span className="tag">Synthetic</span>}
                    {document.partition !== "unassigned" && <span className="tag tag-outline">{document.partition === "test" ? "Held-out test" : "Development"}</span>}
                  </span>
                  <span className="doc-progress">
                    <span className="doc-progress-label">{reviewed} of {total} reviewed</span>
                    <span className="bar"><i style={{ width: `${progress}%` }} /></span>
                  </span>
                  <ArrowRight className="doc-go" size={16} />
                </Link>
                <button className="icon-btn" aria-label={`Delete ${document.filename}`} onClick={() => void remove(document)}>
                  <Trash2 size={15} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
