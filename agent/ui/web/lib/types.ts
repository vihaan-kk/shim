// Types that mirror the Python side exactly. Keep keys in sync with:
//   common/result.py            ToolResult envelope
//   agent/loop.py               Pause and on_event payloads
//   tools/printer/tools.py      printer tool `data` payloads
//   tools/cad/*.py              CAD return dicts
// The frontend never computes geometry; it only displays these values.

// ----- common/result.py -----

export type ToolStatus = "success" | "fixable" | "fatal";

export interface ToolError {
  code: string;
  reason: string;
  valid_range?: unknown;
  hint?: string;
}

export interface ToolResult<D = Record<string, unknown>> {
  status: ToolStatus;
  data: D;
  message: string;
  error: ToolError | null;
  retryable: boolean;
}

// ----- agent/loop.py -----

export type PauseKind = "answer" | "question" | "confirmation" | "stopped";

export interface Pause {
  kind: PauseKind;
  text: string;
  // For "confirmation": { action: "start_print", subject: job_id }
  // For "question": may carry options: string[] from ask_user, shown as buttons.
  details: { action?: string; subject?: string; options?: string[] };
}

// One event from Agent.on_event, plus the final pause of a turn.
export type AgentEvent =
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; result: ToolResult }
  | { type: "navigate"; stage: string }
  | { type: "pause"; pause: Pause };

// ----- tools/printer/tools.py -----

export interface PrinterStatus {
  connection: string | null;
  port: string | null;
  ready: boolean;
  reasons: string[];
  job_state: string | null;
  completion: number | null;
}

export interface PreparedJob {
  job_id: string;
  revision_id: string;
  profile_id: "draft_028" | "demo_020";
  estimated_seconds: number | null;
  filament_m: number | null;
  reused?: boolean;
}

export interface JobProgress {
  job_id: string;
  state: string;
  printer_state?: string;
  completion: number | null;
  time_left_s: number | "estimating";
  next_check_after_s?: number;
}

// ----- tools/cad/validate_socket.py -----

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface CheckCategory {
  passed: boolean;
  checks: Check[];
}

export interface SocketValidation {
  passed: boolean;
  clinical_use: false;
  disclaimer: string;
  socket_model_id: string;
  reference_limb_model_id: string;
  error: unknown;
  categories: Record<string, CheckCategory>;
  measurements?: {
    units: "mm";
    depth_mm: number;
    volume_mm3: number;
    proximal_opening?: {
      status?: string;
      inner_ml_diameter_mm?: number | null;
      inner_ap_diameter_mm?: number | null;
      inner_perimeter_mm?: number | null;
      outer_perimeter_mm?: number | null;
    };
    distal_end?: { axial_wall_mm?: number | null };
    sections: {
      id: string;
      z_mm: number;
      status: string;
      inner_perimeter_mm: number;
      outer_perimeter_mm: number;
      ml_wall_thickness_mm: number;
      ap_wall_thickness_mm: number;
    }[];
  };
}

// ----- README §12 "Print monitoring" (proposed server poll) -----
// The server polls OctoPrint (~2 s) and the page paints this snapshot.
// Fields are optional where OctoPrint omits them; the page says "not reported".

export type PrintStep =
  | "Starting"
  | "Printing"
  | "Pausing"
  | "Paused"
  | "Error"
  | "Link lost"
  | "Cancelled"
  | "Finished";

export interface Temperature {
  actual: number;
  target: number | null;
}

export interface PrintSnapshot {
  job_id: string;
  step: PrintStep;
  observed_at: string; // ISO time of the last successful read
  stale: boolean; // true when the latest poll failed (step is "Link lost")
  completion: number | null; // printed exactly as OctoPrint returned it
  filepos: number | null;
  print_time_s: number | null; // elapsed
  print_time_left_s: number | null; // often missing early in a job
  file: { name: string; size: number | null } | null;
  filament_mm: number | null;
  port: string | null;
  temperatures: { tool0?: Temperature; bed?: Temperature } | null; // virtual-printer reports
  error: string | null;
  // From filepos and the job's G-code (real slicer only): the layer being printed.
  layer: number | null; // 1-based
  layer_count: number | null;
  layer_z: number | null; // mm
}

// GET /api/print/layers: each layer's height and outer-wall paths (flat x, y lists in mm).
export interface PrintLayers {
  job_id: string;
  layer_count: number;
  layers: { z: number; paths: number[][] }[];
}

// ----- page-level state (not a Python type) -----

export interface Measurements {
  length_mm: number | null;
  proximal_circumference_mm: number | null; // station P (required)
  distal_circumference_mm: number | null; // station D (required)
  mid_circumference_mm: number | null; // station M (optional)
  ap_depth_mm: number | null; // at P, optional; both or neither
  ml_width_mm: number | null; // at P, optional; both or neither
  distal_shape: "template" | "rounder" | "more_tapered";
  side: "template" | "left" | "right";
}

export interface LimbRevision {
  revision_id: string; // r0 is the unedited standardized shape
  parent_revision_id: string | null;
  stl_url: string; // resolved by the server from the id; never a filesystem path
}

export interface SocketRevision {
  socket_id: string;
  limb_revision_id: string;
  stl_url: string;
}
