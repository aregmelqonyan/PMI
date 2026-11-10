import type {
  Constraint,
  DocumentItem,
  Evaluation,
  GoldLabel,
  HistoryEvent,
  Meta,
  Partition,
  Passage,
  PlaygroundResult,
  RecordItem,
  RegressionResult,
  RequirementType,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error("The EngiReq server is not reachable. Check that the backend is running.");
  }
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* the default message is used */
    }
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface RecordEdits {
  requirement_type?: RequirementType;
  component?: string | null;
  action_or_state?: string | null;
  condition?: string | null;
  exception?: string | null;
  negated?: boolean;
  constraints?: Constraint[];
}

export const api = {
  meta: () => request<Meta>("/api/meta"),
  documents: () => request<DocumentItem[]>("/api/documents"),
  document: (id: string) => request<DocumentItem>(`/api/documents/${id}`),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ document: DocumentItem; duplicate: boolean }>("/api/documents", { method: "POST", body: form });
  },
  sample: () => request<{ document: DocumentItem; duplicate: boolean }>("/api/documents/sample", { method: "POST" }),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  setPartition: (id: string, partition: Partition) => request<DocumentItem>(`/api/documents/${id}`, json("PATCH", { partition })),
  records: (id: string) => request<RecordItem[]>(`/api/documents/${id}/records`),
  passages: (id: string) => request<Passage[]>(`/api/documents/${id}/passages`),
  edit: (id: string, edits: RecordEdits, reviewer: string, elapsed_ms: number) =>
    request<RecordItem>(`/api/records/${id}`, json("PATCH", { ...edits, reviewer, elapsed_ms })),
  decide: (id: string, decision: "accepted" | "rejected" | "unreviewed", reviewer: string, elapsed_ms: number) =>
    request<RecordItem>(`/api/records/${id}/decision`, json("POST", { decision, reviewer, elapsed_ms })),
  restore: (id: string, reviewer: string) =>
    request<RecordItem>(`/api/records/${id}/restore?reviewer=${encodeURIComponent(reviewer)}`, { method: "POST" }),
  history: (id: string) => request<HistoryEvent[]>(`/api/records/${id}/history`),
  label: (spanId: string, label: GoldLabel | null, reviewer: string) =>
    request<Passage>(`/api/passages/${encodeURIComponent(spanId)}/label`, json("PUT", { label, reviewer })),
  evaluation: (partition: string) => request<Evaluation>(`/api/evaluation?partition=${partition}`),
  regression: () => request<RegressionResult>("/api/evaluation/regression", { method: "POST" }),
  playground: (text: string) => request<PlaygroundResult>("/api/playground", json("POST", { text })),
};

export const pageUrl = (documentId: string, page: number) => `/api/documents/${documentId}/pages/${page}.png`;
export const exportUrl = (documentId: string, format: "jsonl" | "csv", scope: "approved" | "all") =>
  `/api/documents/${documentId}/export?format=${format}&scope=${scope}`;
