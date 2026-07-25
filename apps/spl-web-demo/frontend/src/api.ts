export const API_PREFIX = "/api/demo/v1";

export type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

export type ConstructType =
  | "WORKER"
  | "FLOW"
  | "EXCEPTION_FLOW"
  | "BLOCK"
  | "COMMAND"
  | "REQUIRED_OUTPUT"
  | "CONSTRAINT"
  | "PERSONA"
  | "PERSONA_ASPECT"
  | "AUDIENCE_ASPECT"
  | "CONCEPT"
  | "TYPE"
  | "VARIABLE"
  | "FILE"
  | "API"
  | "API_FUNCTION"
  | "INPUT"
  | "OUTPUT";

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.details = body.error.details;
  }
}

export interface CategorySummary {
  category: string;
  label: string;
  count: number;
}

export interface RunResponse {
  run_id: string;
  editing_run_id: string | null;
  snapshot_id: string | null;
  snapshot_status: string;
  overlay_version: number;
  revision_token: string | null;
  editing_available: boolean;
  projection_status: string;
  construct_count: number;
  issue_count?: number;
  issue_summary?: CategorySummary[];
}

export interface ConstructCard {
  construct_ref: string;
  construct_type: ConstructType;
  title: string;
  status: string;
  payload_summary: Record<string, unknown>;
  provenance_summary: {
    kind: string;
    source_span_count: number;
  };
  source_span_ids: string[];
  parent_ref: string | null;
  construct_path: string[];
}

export interface SplResponse {
  run_id: string;
  snapshot_id: string | null;
  overlay_version: number;
  revision_token: string | null;
  projection_status: string;
  rendered_spl: string | null;
  spl_cards: ConstructCard[];
  message?: string;
}

export interface ConstructListResponse {
  run_id: string;
  snapshot_id: string | null;
  overlay_version: number;
  revision_token: string | null;
  projection_status: string;
  constructs: ConstructCard[];
  message?: string;
}

export interface SpanView {
  span_id: string;
  text: string;
  source_section_id: string | null;
  source_packet_id: string | null;
  section_context: string | null;
  is_placeholder: boolean;
  ambiguity: {
    is_ambiguous: boolean;
    reasons: string[];
    needs_split: boolean;
  };
}

export interface TraceView {
  target_ref: string;
  relation: string;
  explanation: string;
  needs_confirmation: boolean;
  source_section_id: string | null;
  source_packet_id: string | null;
  source_span_ids: string[];
  repair: {
    repair_patch_id: string | null;
    related_diagnostic_id: string | null;
    user_text: string | null;
  } | null;
}

export interface ConstructProvenance {
  construct_ref: string;
  construct_type: ConstructType;
  title: string;
  trace_status: string;
  provenance_kind: string;
  matched_target_refs: string[];
  source_span_ids: string[];
  unresolved_span_ids: string[];
  traces: TraceView[];
  spans: SpanView[];
}

export interface ProvenanceResponse {
  run_id: string;
  snapshot_id: string;
  overlay_version: number;
  revision_token: string;
  projection_status: string;
  construct_ref?: string;
  provenance: ConstructProvenance | null;
  message?: string;
}

export interface SpanResponse {
  run_id: string;
  snapshot_id: string;
  overlay_version: number;
  revision_token: string;
  source_status: string;
  span: SpanView;
}

export interface IssueCard {
  display_id: string;
  issue_id: string;
  category: string;
  title: string;
  impact: string;
  fix_label: string;
  suggested_resolution: string;
  source_excerpt: string | null;
  missing_items: string[];
  repairability: string;
  can_fix: boolean;
  presentation_quality: string;
}

export interface IssueSection {
  section_id: string;
  title: string;
  section_kind: string;
  visible_by_default: boolean;
  items: IssueCard[];
}

export interface IssueListResponse {
  run_id: string;
  snapshot_id: string | null;
  summary: CategorySummary[];
  sections: IssueSection[];
}

export interface RepairOption {
  label: string;
  description: string;
  option_id: string;
  strategy_id: string | null;
  interaction_contract_id: string | null;
  interaction_summary: string | null;
  patch_types: string[];
  verification_lane: string | null;
  availability: string;
  unavailable_reason: string | null;
}

export interface IssueExplanationValue {
  schema_version?: string;
  issue_id?: string;
  language?: string;
  generation_source?: string;
  headline?: string;
  problem?: string;
  impact?: string;
  source_interpretation?: string | null;
  missing_information?: string[];
  options?: Array<{
    option: number;
    label: string;
    description: string;
    available: boolean;
    when_to_choose: string;
    tradeoff: string;
  }>;
  recommended_option?: number | null;
  recommendation_reason?: string;
  questions?: string[];
  generation_warning?: string | null;
  [key: string]: unknown;
}

export interface ExplanationEnvelope {
  status: string;
  value: IssueExplanationValue | null;
  error: string | null;
}

export interface IssueDetailResponse {
  issue: {
    issue_id: string;
    title: string;
    what_was_detected: string;
    missing_items: string[];
    why_it_matters: string;
    suggested_resolution: string;
    source_context: string | null;
    presentation_quality: string;
    available_repairs: RepairOption[];
  };
  explanation: ExplanationEnvelope;
}

export interface ExplanationTriggerResponse {
  run_id: string;
  snapshot_id: string;
  overlay_version: number;
  revision_token: string;
  issue_id: string;
  explanation: ExplanationEnvelope;
  scheduling: {
    requested: boolean;
    accepted: boolean;
  };
}

export interface RepairInputOption {
  option_id: string;
  label: string;
  value: string;
  description: string | null;
}

export interface RepairInputField {
  field_id: string;
  label: string;
  input_type: string;
  required: boolean;
  description: string | null;
  value: unknown;
  options: RepairInputOption[];
  ref_role: string | null;
  object_schema_id: string | null;
  fact_schema_id: string | null;
}

export interface RepairInteractionResponse {
  issue_id: string;
  strategy_id: string;
  option_id: string;
  contract_id: string;
  contract_version: string;
  revision_token: string;
  interaction_kind: string;
  availability: string;
  input_readiness: string;
  fields: RepairInputField[];
  schemas: unknown[];
  validation_errors: Array<Record<string, unknown>>;
  demo_availability?: string;
  unsupported_fields?: string[];
}

export interface SubmitRepairDirectiveRequest {
  issue_id: string;
  strategy_id: string;
  option_id: string;
  contract_id: string;
  contract_version: string;
  revision_token: string;
  field_values: Record<string, unknown>;
  selected_ref_ids: Record<string, string[]>;
  new_fact_declarations: unknown[];
  additional_instruction: string | null;
}

export interface DirectiveValidationError {
  code: string;
  field_id: string | null;
  message: string;
}

export interface RepairDirectiveResponse {
  input_readiness: string;
  directive_id: string | null;
  errors: DirectiveValidationError[];
}

export interface RepairPreviewResponse {
  directive_id: string;
  session_id: string;
  suggestion_id: string;
  preview: {
    preview_id: string | null;
    base_snapshot_id: string | null;
    rendered_preview: string | null;
    typed_artifact_summary: {
      type: string | null;
      construct_node_count: number;
      construct_roles: string[];
    };
    spl_cards: ConstructCard[];
  };
}

export interface VerificationResponse {
  accepted: boolean | null;
  lane: string | null;
  failure_reasons: string[];
  diagnostic_diff_summary: unknown;
  resolved_diagnostic_ids: string[];
  new_blocking_diagnostic_ids: string[];
}

export interface RepairApplyResponse {
  status: string;
  run_id: string;
  snapshot_id: string;
  overlay_version: number;
  revision_token: string;
  verification: VerificationResponse;
  projection_status: string;
  spl: SplResponse;
  issues: IssueListResponse;
}

export interface CreateRunRequest {
  raw_text: string;
  language?: string;
  precompute_issue_explanations?: boolean;
}

export interface CommandResultItem {
  keyword: string;
  name: string;
  data_type: string;
  assignment: string;
}

export interface SplDocumentNode {
  node_ref: string;
  node_kind: "section" | "construct";
  node_type: string;
  construct_ref: string | null;
  parent_node_ref: string | null;
  order: number;
  title: string;
  summary: string | null;
  status: "available" | "partial" | "review_only";
  attributes: Record<string, unknown>;
  provenance_summary: {
    kind: string;
    source_span_count: number;
  } | null;
}

export interface SplDocumentResponse {
  run_id: string;
  snapshot_id: string | null;
  overlay_version: number;
  revision_token: string | null;
  projection_status: string;
  projection_fidelity: "structured" | "render_aligned" | "partial";
  nodes: SplDocumentNode[];
}

export interface SplWebDemoClient {
  createRun(req: CreateRunRequest): Promise<RunResponse>;
  createRunFromSnapshot(snapshotPath: string): Promise<RunResponse>;
  getRun(runId: string): Promise<RunResponse>;
  getSpl(runId: string): Promise<SplResponse>;
  getSplDocument(runId: string): Promise<SplDocumentResponse>;
  listConstructs(runId: string): Promise<ConstructListResponse>;
  getConstructProvenance(runId: string, constructRef: string): Promise<ProvenanceResponse>;
  getSpan(runId: string, spanId: string): Promise<SpanResponse>;
  listIssues(runId: string): Promise<IssueListResponse>;
  getIssue(runId: string, issueId: string): Promise<IssueDetailResponse>;
  triggerIssueExplanation(runId: string, issueId: string): Promise<ExplanationTriggerResponse>;
  getRepairInteraction(
    runId: string,
    issueId: string,
    optionId: string,
    revisionToken: string,
  ): Promise<RepairInteractionResponse>;
  submitRepairDirective(
    runId: string,
    payload: SubmitRepairDirectiveRequest,
  ): Promise<RepairDirectiveResponse>;
  previewRepairDirective(runId: string, directiveId: string): Promise<RepairPreviewResponse>;
  applyRepairPreview(
    runId: string,
    directiveId: string,
    previewId: string,
  ): Promise<RepairApplyResponse>;
}

export function createSplWebDemoClient(baseUrl = ""): SplWebDemoClient {
  const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
    const headers = new Headers(init?.headers);
    headers.set("Accept", "application/json");
    if (init?.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(`${baseUrl}${API_PREFIX}${path}`, {
      ...init,
      headers,
    });
    const body: unknown = await response.json();
    if (!response.ok) {
      if (isApiErrorBody(body)) {
        throw new ApiError(response.status, body);
      }
      throw new Error(`Request failed with HTTP ${response.status}`);
    }
    return body as T;
  };

  return {
    createRun: (req) =>
      request<RunResponse>("/runs", {
        method: "POST",
        body: JSON.stringify({
          raw_text: req.raw_text,
          language: req.language || "zh-CN",
          precompute_issue_explanations: req.precompute_issue_explanations || false,
        }),
      }),
    createRunFromSnapshot: (snapshotPath) =>
      request<RunResponse>("/runs/from-snapshot", {
        method: "POST",
        body: JSON.stringify({ snapshot_path: snapshotPath }),
      }),
    getRun: (runId) => request<RunResponse>(`/runs/${encodeURIComponent(runId)}`),
    getSpl: (runId) => request<SplResponse>(`/runs/${encodeURIComponent(runId)}/spl`),
    getSplDocument: (runId) =>
      request<SplDocumentResponse>(`/runs/${encodeURIComponent(runId)}/spl-document`),
    listConstructs: (runId) =>
      request<ConstructListResponse>(`/runs/${encodeURIComponent(runId)}/constructs`),
    getConstructProvenance: (runId, constructRef) =>
      request<ProvenanceResponse>(
        `/runs/${encodeURIComponent(runId)}/constructs/${encodeURIComponent(constructRef)}/provenance`,
      ),
    getSpan: (runId, spanId) =>
      request<SpanResponse>(
        `/runs/${encodeURIComponent(runId)}/spans/${encodeURIComponent(spanId)}`,
      ),
    listIssues: (runId) =>
      request<IssueListResponse>(`/runs/${encodeURIComponent(runId)}/issues`),
    getIssue: (runId, issueId) =>
      request<IssueDetailResponse>(
        `/runs/${encodeURIComponent(runId)}/issues/${encodeURIComponent(issueId)}`,
      ),
    triggerIssueExplanation: (runId, issueId) =>
      request<ExplanationTriggerResponse>(
        `/runs/${encodeURIComponent(runId)}/issues/${encodeURIComponent(issueId)}/explanation`,
        { method: "POST" },
      ),
    getRepairInteraction: (runId, issueId, optionId, revisionToken) =>
      request<RepairInteractionResponse>(
        `/runs/${encodeURIComponent(runId)}/issues/${encodeURIComponent(issueId)}` +
          `/repair-options/${encodeURIComponent(optionId)}/interaction` +
          `?revision_token=${encodeURIComponent(revisionToken)}`,
      ),
    submitRepairDirective: (runId, payload) =>
      request<RepairDirectiveResponse>(
        `/runs/${encodeURIComponent(runId)}/repair-directives`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      ),
    previewRepairDirective: (runId, directiveId) =>
      request<RepairPreviewResponse>(
        `/runs/${encodeURIComponent(runId)}/repair-directives/` +
          `${encodeURIComponent(directiveId)}/preview`,
        { method: "POST" },
      ),
    applyRepairPreview: (runId, directiveId, previewId) =>
      request<RepairApplyResponse>(
        `/runs/${encodeURIComponent(runId)}/repair-directives/` +
          `${encodeURIComponent(directiveId)}/previews/` +
          `${encodeURIComponent(previewId)}/apply`,
        {
          method: "POST",
          body: JSON.stringify({ user_confirmation: true }),
        },
      ),
  };
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (!value || typeof value !== "object" || !("error" in value)) {
    return false;
  }
  const error = (value as { error?: unknown }).error;
  return Boolean(
    error &&
      typeof error === "object" &&
      typeof (error as { code?: unknown }).code === "string" &&
      typeof (error as { message?: unknown }).message === "string",
  );
}
