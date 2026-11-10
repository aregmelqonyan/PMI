export type Operator = "<=" | "<" | ">=" | ">" | "=";
export type Overall = "pass" | "warn" | "abstain";
export type ReviewStatus = "unreviewed" | "accepted" | "edited" | "rejected";
export type GoldLabel = "requirement" | "non_requirement" | "uncertain";
export type Partition = "unassigned" | "dev" | "test";
export type RequirementType = "functional" | "performance" | "interface" | "safety" | "environmental" | "other";

export interface Constraint {
  parameter: string | null;
  operator: Operator | null;
  value: number | null;
  tolerance: number | null;
  unit: string | null;
  condition: string | null;
  surface_text: string;
  start_char: number | null;
  end_char: number | null;
}

export interface Evidence {
  page: number | null;
  section: string | null;
  block_id: string;
  start_char: number;
  end_char: number;
  quoted_text: string;
  rects: number[][];
}

export interface Requirement {
  requirement_id: string;
  document_id: string;
  source_sha256: string;
  span_id: string;
  source_label: string | null;
  is_requirement: boolean;
  modality: string;
  requirement_type: RequirementType;
  component: string | null;
  action_or_state: string | null;
  negated: boolean;
  condition: string | null;
  exception: string | null;
  constraints: Constraint[];
  evidence: Evidence;
  quality_flags: string[];
  trace: string[];
  method: string;
}

export interface Check {
  id: string;
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface Validation {
  overall: Overall;
  schema_status: string;
  source_alignment_status: string;
  checks: Check[];
}

export interface RecordItem {
  id: string;
  document_id: string;
  record: Requirement;
  validation: Validation;
  review_status: ReviewStatus;
  reviewer: string | null;
  elapsed_ms: number;
  updated_at: string | null;
  original_overall: Overall;
}

export interface Passage {
  span_id: string;
  document_id: string;
  page: number | null;
  block_id: string;
  section: string | null;
  start_char: number;
  end_char: number;
  text: string;
  rects: number[][];
  detected: boolean;
  modality: string;
  reason: string;
  record_ids: string[];
  gold_label: GoldLabel | null;
  labeled_by: string | null;
}

export interface PageInfo {
  page: number;
  width: number;
  height: number;
}

export interface DocumentItem {
  id: string;
  filename: string;
  sha256: string;
  uploaded_at: string;
  method: string;
  partition: Partition;
  synthetic: boolean;
  pages: PageInfo[];
  warnings: string[];
  records: { total: number; reviewed: number; accepted: number; edited: number; rejected: number };
  passages: { total: number; labeled: number };
}

export interface HistoryEvent {
  id: number;
  at: string;
  actor: string;
  action: string;
  elapsed_ms: number;
  note: string | null;
}

export interface Prf {
  precision: number | null;
  recall: number | null;
  f1: number | null;
}

export interface Confusion {
  tp: number;
  fp: number;
  fn: number;
  tn: number;
}

export interface DetectionError {
  kind: "fp" | "fn";
  document_id: string;
  filename: string | null;
  span_id: string;
  page: number | null;
  text: string;
  reason: string;
}

export interface Detection extends Prf {
  confusion: Confusion;
  macro_f1: number | null;
  f1_ci95: [number, number] | null;
  labeled: number;
  uncertain_excluded: number;
  documents: ({ document_id: string; filename: string | null; labeled: number } & Confusion & Prf)[];
  errors: DetectionError[];
}

export interface OutcomeRow {
  total: number;
  accepted: number;
  edited: number;
  rejected: number;
  unreviewed: number;
}

export interface Evaluation {
  partition: string;
  documents: number;
  synthetic_documents: number;
  detection: Detection;
  review: {
    total_records: number;
    status: Record<ReviewStatus, number>;
    reviewed: number;
    accepted_unchanged_rate: number | null;
    kept_rate: number | null;
    median_ms_per_kept_record: number | null;
    validator_outcomes: Record<Overall, OutcomeRow>;
    field_edits: Record<string, number>;
  };
}

export interface RegressionResult {
  cases: number;
  confusion: Confusion;
  detection: Prf;
  constraints: Prf;
  constraint_counts: { tp: number; fp: number; fn: number };
  failures: { text: string; expected_detected: boolean; detected: boolean; expected_records: number | null; extracted_records: number }[];
}

export interface PlaygroundResult {
  source: string;
  passages: Passage[];
  records: { record: Requirement; validation: Validation }[];
}

export interface Meta {
  method: string;
  units: string[];
  flags: Record<string, string>;
}
