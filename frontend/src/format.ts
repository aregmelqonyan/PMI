import type { Constraint, Operator } from "./types";

const OPERATOR_SYMBOL: Record<Operator, string> = { "<=": "≤", "<": "<", ">=": "≥", ">": ">", "=": "=" };
const UNIT_SYMBOL: Record<string, string> = {
  degC: "°C",
  degF: "°F",
  um: "µm",
  "N.m": "N·m",
  ohm: "Ω",
  kohm: "kΩ",
  Mohm: "MΩ",
  deg: "°",
  "m/s2": "m/s²",
  "W/m2": "W/m²",
};

export const operatorSymbol = (operator: Operator | null) => (operator ? OPERATOR_SYMBOL[operator] : "?");
export const unitSymbol = (unit: string | null) => (unit ? UNIT_SYMBOL[unit] ?? unit : "");

export function humanize(value: string | null | undefined): string {
  if (!value) return "";
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function constraintValue(constraint: Constraint): string {
  if (constraint.value === null) return "not stated";
  const number = constraint.value.toLocaleString("en-US", { maximumFractionDigits: 6 });
  const tolerance = constraint.tolerance !== null ? ` ± ${constraint.tolerance}` : "";
  const unit = unitSymbol(constraint.unit);
  return `${number}${tolerance}${unit ? ` ${unit}` : ""}`;
}

export const score = (value: number | null | undefined, digits = 3) => (value === null || value === undefined ? "—" : value.toFixed(digits));
export const percent = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`);

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`;
}

export function dateTime(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function loadReviewer(): string {
  try {
    return localStorage.getItem("engireq.reviewer") || "reviewer";
  } catch {
    return "reviewer";
  }
}

export function saveReviewer(name: string): void {
  try {
    localStorage.setItem("engireq.reviewer", name);
  } catch {
    /* the name then lasts only for this session */
  }
}
