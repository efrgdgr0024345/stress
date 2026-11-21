export type Point = [number, number];
export interface Sheet {
  id: string;
  source_id: string;
  filename: string;
  sha256: string;
  page_index: number;
  width: number;
  height: number;
  rotation: number;
  printed_id: string;
  line_id: string;
  format: string;
  text: string;
  axis: Point | null;
  table: Point | null;
}
export interface NodeInstance {
  sheet_id: string;
  anchor: Point;
  bubble: Point;
}
export interface PipeNode {
  id: string;
  number: number;
  line_id: string;
  route: string;
  takeoff_id?: string | null;
  order: number;
  kind: string;
  station_mm: string | null;
  dimension_input?: string;
  evidence: string;
  reasons: string[];
  support_gap_mm: string | null;
  instances: NodeInstance[];
}
export interface Material {
  id: string;
  sheet_id: string;
  item_no: string;
  family: string;
  description: string;
  size: string;
  quantity: number;
  observed: number;
  evidence: string;
  catalog_match?: {
    status?: string;
    catalog_version_id: string;
    spec: Record<string, string>;
    record: {
      quality: string;
      source: string;
      weight_n: string | null;
      length_mm: string | null;
      half_weight_n?: string | null;
      full_weight_n?: string | null;
      [key: string]: unknown;
    };
  };
}
export interface DrawingNote {
  id: string;
  sheet_id: string;
  kind: "FreeText" | "Square" | "Circle" | "Line";
  rect: [number, number, number, number];
  text: string;
  color: string;
}
export interface Issue {
  code: string;
  severity: string;
  message: string;
  node?: number;
  point_id?: string;
  material_id?: string;
}
export interface Project {
  id: string;
  title: string;
  line_id: string;
  description: string;
  version: number;
  status: string;
  sample: boolean;
  created: string;
  updated: string;
  sheets: Sheet[];
  nodes: PipeNode[];
  materials: Material[];
  issues: Issue[];
  materials_reviewed: boolean;
  layout_reviewed: boolean;
  annotations?: DrawingNote[];
  graph?: {
    points: string[];
    edges: { from: string; to: string; route: string; line_id: string }[];
    source: string;
  };
}
export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
}
export interface Artifact {
  id: string;
  revision: number;
  filename: string;
  created: string;
  count: number;
}
export interface History {
  events: {
    id: string;
    actor: string;
    action: string;
    detail: string;
    created: string;
  }[];
  artifacts: Artifact[];
  revisions: { version: number; updated: string }[];
}
export const label = (v: string) =>
  v
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const value = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : JSON.stringify(value.detail),
    );
  }
  return response.json();
}
