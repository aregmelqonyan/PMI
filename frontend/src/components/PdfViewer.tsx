import { ChevronLeft, ChevronRight, Minus, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { pageUrl } from "../api";
import type { PageInfo } from "../types";

export interface Highlight {
  key: string;
  rects: number[][];
  tone: "pass" | "warn" | "abstain" | "muted" | "rejected" | "accepted";
  label: string;
}

interface Props {
  documentId: string;
  pages: PageInfo[];
  page: number;
  onPage: (page: number) => void;
  highlights: Highlight[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  focusToken: number;
  legend: "validation" | "detection";
}

export default function PdfViewer({ documentId, pages, page, onPage, highlights, selectedKey, onSelect, focusToken, legend }: Props) {
  const [zoom, setZoom] = useState(1);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const selectedRef = useRef<HTMLButtonElement | null>(null);
  const info = pages[page - 1];

  useEffect(() => {
    setLoading(true);
    setFailed(false);
  }, [documentId, page]);

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
  }, [focusToken, selectedKey, page, loading]);

  if (!info) return null;
  const left = (v: number) => `${(v / info.width) * 100}%`;
  const top = (v: number) => `${(v / info.height) * 100}%`;

  return (
    <section className="pdf" aria-label="Source document">
      <div className="pdf-toolbar">
        <div className="pager">
          <button className="icon-btn" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
            <ChevronLeft size={16} />
          </button>
          <span>
            Page{" "}
            <input
              aria-label="Page number"
              type="number"
              min={1}
              max={pages.length}
              value={page}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (next >= 1 && next <= pages.length) onPage(next);
              }}
            />{" "}
            of {pages.length}
          </span>
          <button className="icon-btn" disabled={page >= pages.length} onClick={() => onPage(page + 1)} aria-label="Next page">
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="legend" aria-label="Highlight legend">
          {legend === "validation" ? (
            <>
              <span><i className="swatch tone-pass" />Verified</span>
              <span><i className="swatch tone-warn" />Attention</span>
              <span><i className="swatch tone-abstain" />Abstained</span>
            </>
          ) : (
            <>
              <span><i className="swatch tone-pass" />Detected</span>
              <span><i className="swatch tone-muted" />Not detected</span>
            </>
          )}
        </div>
        <div className="pager">
          <button className="icon-btn" disabled={zoom <= 0.6} onClick={() => setZoom((z) => +(z - 0.2).toFixed(1))} aria-label="Zoom out">
            <Minus size={15} />
          </button>
          <span className="zoom">{Math.round(zoom * 100)}%</span>
          <button className="icon-btn" disabled={zoom >= 2.4} onClick={() => setZoom((z) => +(z + 0.2).toFixed(1))} aria-label="Zoom in">
            <Plus size={15} />
          </button>
        </div>
      </div>
      <div className="pdf-scroll">
        <div className="pdf-page" style={{ width: `${zoom * 100}%`, aspectRatio: `${info.width} / ${info.height}` }}>
          <img
            src={pageUrl(documentId, page)}
            alt={`Page ${page} of the source document`}
            draggable={false}
            onLoad={() => setLoading(false)}
            onError={() => {
              setLoading(false);
              setFailed(true);
            }}
          />
          {loading && <div className="pdf-loading">Rendering page…</div>}
          {failed && <div className="pdf-loading">This page could not be rendered.</div>}
          {highlights.flatMap((highlight) =>
            highlight.rects.map((rect, index) => {
              const selected = highlight.key === selectedKey;
              return (
                <button
                  key={`${highlight.key}-${index}`}
                  ref={selected && index === 0 ? selectedRef : undefined}
                  className={`hl tone-${highlight.tone}${selected ? " selected" : ""}`}
                  title={highlight.label}
                  aria-label={highlight.label}
                  style={{
                    left: left(rect[0] - 1.5),
                    top: top(rect[1] - 0.5),
                    width: left(rect[2] - rect[0] + 3),
                    height: top(rect[3] - rect[1] + 1),
                  }}
                  onClick={() => onSelect(highlight.key)}
                />
              );
            }),
          )}
        </div>
      </div>
    </section>
  );
}
