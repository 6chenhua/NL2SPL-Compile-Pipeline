import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import App from "./App";
import { ApiError } from "./api";
import type {
  ConstructListResponse,
  IssueDetailResponse,
  IssueListResponse,
  ProvenanceResponse,
  RepairApplyResponse,
  RepairInteractionResponse,
  RepairPreviewResponse,
  RunResponse,
  SpanResponse,
  SplResponse,
  SplWebDemoClient,
  SubmitRepairDirectiveRequest,
  CreateRunRequest,
  SplDocumentResponse,
} from "./api";

beforeEach(() => {
  window.history.pushState(null, "", "/");
});

const run: RunResponse = {
  run_id: "demo",
  editing_run_id: "demo",
  snapshot_id: "snap-demo",
  snapshot_status: "available",
  overlay_version: 0,
  revision_token: "demo:snap-demo:0",
  editing_available: true,
  projection_status: "available",
  construct_count: 4,
  issue_count: 1,
};

const constructs: ConstructListResponse = {
  run_id: "demo",
  snapshot_id: "snap-demo",
  overlay_version: 0,
  revision_token: "demo:snap-demo:0",
  projection_status: "available",
  constructs: [
    {
      construct_ref: "worker-main",
      construct_type: "WORKER",
      title: "MainWorker",
      status: "available",
      payload_summary: {
        worker_name: "MainWorker",
        worker_kind: "main",
        command_count: 1,
      },
      provenance_summary: { kind: "source_backed", source_span_count: 1 },
      source_span_ids: ["s1"],
      parent_ref: null,
      construct_path: ["worker-main"],
    },
    {
      construct_ref: "flow-main",
      construct_type: "FLOW",
      title: "Main Flow",
      status: "available",
      payload_summary: {
        worker_name: "MainWorker",
        flow_id: "main",
        flow_kind: "main",
        block_count: 1,
      },
      provenance_summary: { kind: "source_backed", source_span_count: 1 },
      source_span_ids: ["s1"],
      parent_ref: "worker-main",
      construct_path: ["worker-main", "flow-main"],
    },
    {
      construct_ref: "block-main",
      construct_type: "BLOCK",
      title: "SEQUENTIAL Block b1",
      status: "available",
      payload_summary: {
        worker_name: "MainWorker",
        flow_id: "main",
        block_id: "b1",
        block_type: "SEQUENTIAL",
      },
      provenance_summary: { kind: "source_backed", source_span_count: 1 },
      source_span_ids: ["s1"],
      parent_ref: "flow-main",
      construct_path: ["worker-main", "flow-main", "block-main"],
    },
    {
      construct_ref: "command-one",
      construct_type: "COMMAND",
      title: "st_1: Collect approved evidence",
      status: "available",
      payload_summary: {
        worker_name: "MainWorker",
        command_id: "st_1",
        text: "Collect approved evidence",
        command_type: "GENERAL_COMMAND",
        flow_ref: "main",
        block_ref: "b1",
        hierarchy_status: "placed",
      },
      provenance_summary: { kind: "direct", source_span_count: 1 },
      source_span_ids: ["s1"],
      parent_ref: "block-main",
      construct_path: ["worker-main", "flow-main", "block-main", "command-one"],
    },
  ],
};

const spl: SplResponse = {
  run_id: "demo",
  snapshot_id: "snap-demo",
  overlay_version: 0,
  revision_token: "demo:snap-demo:0",
  projection_status: "available",
  rendered_spl: "[DEFINE_AGENT: MainWorker]",
  spl_cards: constructs.constructs,
};

const provenance: ProvenanceResponse = {
  run_id: "demo",
  snapshot_id: "snap-demo",
  overlay_version: 0,
  revision_token: "demo:snap-demo:0",
  projection_status: "available",
  provenance: {
    construct_ref: "worker-main",
    construct_type: "WORKER",
    title: "MainWorker",
    trace_status: "available",
    provenance_kind: "direct",
    matched_target_refs: ["worker:MainWorker"],
    source_span_ids: ["s1"],
    unresolved_span_ids: [],
    traces: [
      {
        target_ref: "worker:MainWorker",
        relation: "direct",
        explanation: "Worker maps to the source-backed orchestration requirement.",
        needs_confirmation: false,
        source_section_id: "sec-1",
        source_packet_id: "packet-1",
        source_span_ids: ["s1"],
        repair: null,
      },
    ],
    spans: [
      {
        span_id: "s1",
        text: "Coordinate the workflow using approved evidence.",
        source_section_id: "sec-1",
        source_packet_id: "packet-1",
        section_context: "Workflow",
        is_placeholder: false,
        ambiguity: { is_ambiguous: false, reasons: [], needs_split: false },
      },
    ],
  },
};

const commandProvenance: ProvenanceResponse = {
  ...provenance,
  provenance: {
    ...provenance.provenance!,
    construct_ref: "command-one",
    construct_type: "COMMAND",
    title: "st_1: Collect approved evidence",
    matched_target_refs: ["step:st_1"],
    traces: [
      {
        ...provenance.provenance!.traces[0],
        target_ref: "step:st_1",
        explanation: "Command provenance must remain selected.",
      },
    ],
    spans: [
      {
        ...provenance.provenance!.spans[0],
        text: "Collect approved evidence from allowed sources.",
      },
    ],
  },
};

const span: SpanResponse = {
  run_id: "demo",
  snapshot_id: "snap-demo",
  overlay_version: 0,
  revision_token: "demo:snap-demo:0",
  source_status: "available",
  span: provenance.provenance!.spans[0],
};

const issues: IssueListResponse = {
  run_id: "demo",
  snapshot_id: "snap-demo",
  summary: [{ category: "worker_delegation", label: "Worker delegation", count: 1 }],
  sections: [
    {
      section_id: "editable",
      title: "Editable issues",
      section_kind: "editable",
      visible_by_default: true,
      items: [
        {
          display_id: "I-1",
          issue_id: "issue-1",
          category: "worker_delegation",
          title: "Worker delegation is underspecified",
          impact: "The delegated task cannot be materialized safely.",
          fix_label: "Review delegation",
          suggested_resolution: "Clarify the task boundary.",
          source_excerpt: "Delegate source gathering.",
          missing_items: ["task boundary"],
          repairability: "editable",
          can_fix: true,
          presentation_quality: "complete",
        },
      ],
    },
  ],
};

const issueDetail: IssueDetailResponse = {
  issue: {
    issue_id: "issue-1",
    title: "Worker delegation is underspecified",
    what_was_detected: "A delegation signal lacks a complete task boundary.",
    missing_items: ["task boundary"],
    why_it_matters: "The compiler cannot safely materialize a child worker.",
    suggested_resolution: "Keep the task in the main flow or define a child worker.",
    source_context: "Delegate source gathering.",
    presentation_quality: "complete",
    available_repairs: [
      {
        label: "Keep in main flow",
        description: "Convert the task to a main-flow step.",
        option_id: "keep_in_main_flow",
        strategy_id: "worker_delegation.complete_closure.v2",
        interaction_contract_id: "worker_delegation.keep_in_main_flow.v1",
        interaction_summary: "Confirm the task selection.",
        patch_types: ["ConvertDelegationIntentToMainFlowStep"],
        verification_lane: "B",
        availability: "available",
        unavailable_reason: null,
      },
    ],
  },
  explanation: {
    status: "ready",
    error: null,
    value: {
      schema_version: "issue_explanation.v1",
      headline: "Clarify the worker boundary",
      problem: "The task is delegable but its contract is incomplete.",
      impact: "An incomplete worker boundary cannot be rendered safely.",
      recommendation_reason: "Keep it in the main flow unless a complete contract is available.",
      questions: [],
    },
  },
};

const repairInteraction: RepairInteractionResponse = {
  issue_id: "issue-1",
  strategy_id: "worker_delegation.complete_closure.v2",
  option_id: "keep_in_main_flow",
  contract_id: "worker_delegation.keep_in_main_flow.v1",
  contract_version: "1.0",
  revision_token: "demo:snap-demo:0",
  interaction_kind: "structured_with_notes",
  availability: "available",
  input_readiness: "input_required",
  fields: [
    {
      field_id: "task_selection",
      label: "Task boundary",
      input_type: "single_choice",
      required: true,
      description: null,
      value: null,
      options: [
        {
          option_id: "source_gathering",
          label: "Source gathering",
          value: "source gathering",
          description: null,
        },
        {
          option_id: "template_matching",
          label: "Template matching",
          value: "template matching",
          description: null,
        },
      ],
      ref_role: null,
      object_schema_id: null,
      fact_schema_id: null,
    },
    {
      field_id: "additional_instruction",
      label: "Additional instruction",
      input_type: "long_text",
      required: false,
      description: null,
      value: null,
      options: [],
      ref_role: null,
      object_schema_id: null,
      fact_schema_id: null,
    },
  ],
  schemas: [],
  validation_errors: [],
};

const repairPreview: RepairPreviewResponse = {
  directive_id: "directive-1",
  session_id: "session-1",
  suggestion_id: "suggestion-1",
  preview: {
    preview_id: "preview-1",
    base_snapshot_id: "snap-demo",
    rendered_preview: "COMMAND Collect approved sources in the main flow.",
    typed_artifact_summary: {
      type: "WorkerDelegationPreviewArtifact",
      construct_node_count: 1,
      construct_roles: ["main_flow_step"],
    },
    spl_cards: [],
  },
};

const issuesAfterApply: IssueListResponse = {
  run_id: "demo",
  snapshot_id: "snap-demo",
  summary: [],
  sections: [],
};

const runAfterApply: RunResponse = {
  ...run,
  overlay_version: 1,
  revision_token: "demo:snap-demo:1",
  projection_status: "projection_unavailable",
  construct_count: 0,
  issue_count: 0,
};

const splAfterApply: SplResponse = {
  ...spl,
  overlay_version: 1,
  revision_token: "demo:snap-demo:1",
  projection_status: "projection_unavailable",
  rendered_spl: null,
  spl_cards: [],
  message: "Repair applied and verification accepted, but patched SPL projection is unavailable.",
};

const constructsAfterApply: ConstructListResponse = {
  ...constructs,
  overlay_version: 1,
  revision_token: "demo:snap-demo:1",
  projection_status: "projection_unavailable",
  constructs: [],
  message: "Patched Construct projection is unavailable.",
};

const repairApplyResult: RepairApplyResponse = {
  status: "applied",
  run_id: "demo",
  snapshot_id: "snap-demo",
  overlay_version: 1,
  revision_token: "demo:snap-demo:1",
  verification: {
    accepted: true,
    lane: "B",
    failure_reasons: [],
    diagnostic_diff_summary: null,
    resolved_diagnostic_ids: ["diag-worker"],
    new_blocking_diagnostic_ids: [],
  },
  projection_status: "projection_unavailable",
  spl: splAfterApply,
  issues: issuesAfterApply,
};

const splDocument: SplDocumentResponse = {
  run_id: "demo",
  snapshot_id: "snap-demo",
  overlay_version: 0,
  revision_token: "demo:snap-demo:0",
  projection_status: "available",
  projection_fidelity: "render_aligned",
  nodes: [
    {
      node_ref: "agent-main",
      node_kind: "section",
      node_type: "AGENT",
      construct_ref: null,
      parent_node_ref: null,
      order: 1,
      title: "MainWorker",
      summary: "Coordinate the workflow.",
      status: "available",
      attributes: {},
      provenance_summary: null,
    },
    {
      node_ref: "section:workers",
      node_kind: "section",
      node_type: "WORKERS",
      construct_ref: null,
      parent_node_ref: "agent-main",
      order: 90,
      title: "Workers",
      summary: null,
      status: "available",
      attributes: {},
      provenance_summary: null,
    },
    {
      node_ref: "worker-main",
      node_kind: "construct",
      node_type: "WORKER",
      construct_ref: "worker-main",
      parent_node_ref: "section:workers",
      order: 91,
      title: "MainWorker",
      summary: "Coordinate the workflow using approved evidence.",
      status: "available",
      attributes: {
        worker_name: "MainWorker",
        worker_kind: "main",
        description: "Coordinate the workflow using approved evidence.",
      },
      provenance_summary: { kind: "source_backed", source_span_count: 1 },
    },
    {
      node_ref: "flow-main",
      node_kind: "construct",
      node_type: "FLOW",
      construct_ref: "flow-main",
      parent_node_ref: "worker-main",
      order: 10,
      title: "Main Flow",
      summary: null,
      status: "available",
      attributes: {
        worker_name: "MainWorker",
        flow_id: "main",
        flow_kind: "main",
        block_count: 1,
      },
      provenance_summary: { kind: "source_backed", source_span_count: 1 },
    },
    {
      node_ref: "block-main",
      node_kind: "construct",
      node_type: "BLOCK",
      construct_ref: "block-main",
      parent_node_ref: "flow-main",
      order: 11,
      title: "SEQUENTIAL Block b1",
      summary: null,
      status: "available",
      attributes: {
        worker_name: "MainWorker",
        flow_id: "main",
        block_id: "b1",
        block_type: "SEQUENTIAL",
      },
      provenance_summary: { kind: "source_backed", source_span_count: 1 },
    },
    {
      node_ref: "command-one",
      node_kind: "construct",
      node_type: "COMMAND",
      construct_ref: "command-one",
      parent_node_ref: "block-main",
      order: 12,
      title: "Collect approved evidence",
      summary: null,
      status: "available",
      attributes: {
        step_id: "st_1",
        text: "Collect approved evidence",
        command_type: "GENERAL_COMMAND",
      },
      provenance_summary: { kind: "direct", source_span_count: 1 },
    },
  ],
};

function createClient(overrides: Partial<SplWebDemoClient> = {}): SplWebDemoClient {
  return {
    createRun: async () => run,
    createRunFromSnapshot: async () => run,
    getRun: async () => run,
    getSpl: async () => spl,
    getSplDocument: async () => splDocument,
    listConstructs: async () => constructs,
    getConstructProvenance: async () => provenance,
    getSpan: async () => span,
    listIssues: async () => issues,
    getIssue: async () => issueDetail,
    triggerIssueExplanation: async () => ({
      run_id: "demo",
      snapshot_id: "snap-demo",
      overlay_version: 0,
      revision_token: "demo:snap-demo:0",
      issue_id: "issue-1",
      explanation: issueDetail.explanation,
      scheduling: { requested: false, accepted: false },
    }),
    getRepairInteraction: async () => repairInteraction,
    submitRepairDirective: async () => ({
      input_readiness: "input_complete",
      directive_id: "directive-1",
      errors: [],
    }),
    previewRepairDirective: async () => repairPreview,
    applyRepairPreview: async () => repairApplyResult,
    ...overrides,
  };
}

describe("SPL inspection workbench", () => {
  it("hydrates a direct workbench URL and responds to browser history changes", async () => {
    window.history.pushState(null, "", "/runs/demo");
    render(<App client={createClient()} />);

    expect(await screen.findByText("demo:snap-demo:0")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/runs/demo");

    await userEvent.setup().click(screen.getByRole("button", { name: "New generation" }));
    expect(window.location.pathname).toBe("/");
    expect(screen.getByRole("heading", { name: "Generate SPL" })).toBeInTheDocument();

    act(() => {
      window.history.pushState(null, "", "/runs/demo");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(await screen.findByText("demo:snap-demo:0")).toBeInTheDocument();
  });

  it("compiles an initial requirement and hydrates the public run read models", async () => {
    const user = userEvent.setup();
    const createRun = vi.fn(async (_req: CreateRunRequest) => run);
    render(<App client={createClient({ createRun })} />);

    await user.click(screen.getByRole("button", { name: "Generate SPL" }));

    expect(createRun).toHaveBeenCalledTimes(1);
    expect(createRun.mock.calls[0][0].raw_text).toContain("internal newsletter coordinator agent");
    expect(await screen.findByText("demo:snap-demo:0")).toBeInTheDocument();
    expect((await screen.findAllByText("MainWorker")).length).toBeGreaterThanOrEqual(1);
  });

  it("loads a snapshot and displays Construct, provenance, issue, and explanation DTOs", async () => {
    const user = userEvent.setup();
    const createRun = vi.fn(async () => run);
    render(<App client={createClient({ createRunFromSnapshot: createRun })} />);

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));

    expect(createRun).toHaveBeenCalledWith("examples/output/demo/spl_editing_snapshot.json");
    expect(await screen.findByText("demo:snap-demo:0")).toBeInTheDocument();
    expect((await screen.findAllByText("MainWorker")).length).toBeGreaterThanOrEqual(1);
    expect(
      await screen.findByText("Coordinate the workflow using approved evidence."),
    ).toBeInTheDocument();
    expect(screen.getByText("FLOW · MAIN")).toBeInTheDocument();
    expect(screen.getByText("BLOCK · SEQUENTIAL")).toBeInTheDocument();
    expect(screen.getByText("COMMAND")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Problems" })).toBeInTheDocument();
    expect(
      (await screen.findAllByText("Worker delegation is underspecified")).length,
    ).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText("Clarify the worker boundary")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configure repair" })).toBeInTheDocument();
  });

  it("shows only concrete source text in the hover provenance tooltip", async () => {
    const user = userEvent.setup();
    const getProvenance = vi.fn(async (_runId: string, constructRef: string) =>
      constructRef === "command-one" ? commandProvenance : provenance,
    );
    render(<App client={createClient({ getConstructProvenance: getProvenance })} />);

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    const command = await screen.findByRole("button", { name: /Collect approved evidence/i });
    await user.hover(command);

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Collect approved evidence from allowed sources.");
    expect(tooltip).not.toHaveTextContent("s1");
    expect(tooltip).not.toHaveTextContent("step:st_1");
  });

  it("opens a unified Problems row by keyboard", async () => {
    const user = userEvent.setup();
    const getIssue = vi.fn(async () => issueDetail);
    render(<App client={createClient({ getIssue })} />);

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    const row = await screen.findByRole("row", {
      name: "Open issue Worker delegation is underspecified",
    });
    row.focus();
    await user.keyboard("{Enter}");

    expect(getIssue).toHaveBeenCalledWith("demo", "issue-1");
    expect(await screen.findByText("Clarify the worker boundary")).toBeInTheDocument();
  });

  it("opens complete source text through the dedicated span API", async () => {
    const user = userEvent.setup();
    const getSpan = vi.fn(async () => span);
    render(<App client={createClient({ getSpan })} />);

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(
      await screen.findByRole("button", { name: /Collect approved evidence/i }),
    );
    const inspector = screen.getByLabelText("Properties inspector");
    await user.click(within(inspector).getByRole("button", { name: "Provenance" }));
    await user.click(await screen.findByRole("button", { name: /Open source detail/i }));

    expect(getSpan).toHaveBeenCalledWith("demo", "s1");
    const detail = await screen.findByLabelText("Source detail");
    expect(detail).toHaveTextContent("Coordinate the workflow using approved evidence.");
    expect(detail).toHaveTextContent("Workflow");
  });

  it("ignores a stale provenance response after the user selects another Construct", async () => {
    const user = userEvent.setup();
    let resolveWorker: ((value: ProvenanceResponse) => void) | undefined;
    const workerResponse = new Promise<ProvenanceResponse>((resolve) => {
      resolveWorker = resolve;
    });
    const getProvenance = vi.fn(async (_runId: string, constructRef: string) =>
      constructRef === "worker-main" ? workerResponse : commandProvenance,
    );
    render(
      <App client={createClient({ getConstructProvenance: getProvenance })} />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(
      await screen.findByRole("button", { name: /Collect approved evidence/i }),
    );
    const inspector = screen.getByLabelText("Properties inspector");
    await user.click(within(inspector).getByRole("button", { name: "Provenance" }));

    expect(
      await within(inspector).findByText("Collect approved evidence from allowed sources."),
    ).toBeInTheDocument();
    await act(async () => {
      resolveWorker?.(provenance);
      await workerResponse;
    });
    expect(
      within(inspector).queryByText("Coordinate the workflow using approved evidence."),
    ).not.toBeInTheDocument();
    expect(
      within(inspector).getByText("Collect approved evidence from allowed sources."),
    ).toBeInTheDocument();
  });

  it("requests a missing explanation without invoking repair controls", async () => {
    const user = userEvent.setup();
    const missingDetail: IssueDetailResponse = {
      ...issueDetail,
      explanation: { status: "missing", value: null, error: null },
    };
    const trigger = vi.fn(async () => ({
      run_id: "demo",
      snapshot_id: "snap-demo",
      overlay_version: 0,
      revision_token: "demo:snap-demo:0",
      issue_id: "issue-1",
      explanation: { status: "pending", value: null, error: null },
      scheduling: { requested: true, accepted: true },
    }));
    render(
      <App
        client={createClient({
          getIssue: async () => missingDetail,
          triggerIssueExplanation: trigger,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(await screen.findByRole("button", { name: "Request explanation" }));

    expect(trigger).toHaveBeenCalledWith("demo", "issue-1");
    expect(await screen.findByText("Explanation generation is pending")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply/i })).not.toBeInTheDocument();
  });

  it("renders the verified repair interaction and submits option values without fabricating fields", async () => {
    const user = userEvent.setup();
    const getInteraction = vi.fn(async () => repairInteraction);
    const submitDirective = vi.fn(
      async (_runId: string, _payload: SubmitRepairDirectiveRequest) => ({
        input_readiness: "input_complete",
        directive_id: "directive-1",
        errors: [],
      }),
    );
    const previewDirective = vi.fn(async () => repairPreview);
    render(
      <App
        client={createClient({
          getRepairInteraction: getInteraction,
          submitRepairDirective: submitDirective,
          previewRepairDirective: previewDirective,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(await screen.findByRole("button", { name: "Configure repair" }));

    expect(getInteraction).toHaveBeenCalledWith(
      "demo",
      "issue-1",
      "keep_in_main_flow",
      "demo:snap-demo:0",
    );
    const generate = await screen.findByRole("button", { name: "Generate preview" });
    expect(generate).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "Source gathering" }));
    await user.type(
      screen.getByLabelText("Additional instruction"),
      "Keep the evidence check explicit.",
    );
    await user.click(generate);

    expect(submitDirective).toHaveBeenCalledWith("demo", {
      issue_id: "issue-1",
      strategy_id: "worker_delegation.complete_closure.v2",
      option_id: "keep_in_main_flow",
      contract_id: "worker_delegation.keep_in_main_flow.v1",
      contract_version: "1.0",
      revision_token: "demo:snap-demo:0",
      field_values: { task_selection: "source gathering" },
      selected_ref_ids: {},
      new_fact_declarations: [],
      additional_instruction: "Keep the evidence check explicit.",
    });
    expect(previewDirective).toHaveBeenCalledWith("demo", "directive-1");
    expect(await screen.findByLabelText("Repair preview")).toHaveTextContent(
      "WorkerDelegationPreviewArtifact",
    );
    expect(screen.getByLabelText("Repair identities")).toHaveTextContent("preview-1");
    expect(screen.getByRole("button", { name: "Apply repair" })).toBeInTheDocument();
  });

  it("cancels a preview locally without calling apply", async () => {
    const user = userEvent.setup();
    const applyPreview = vi.fn(async () => repairApplyResult);
    render(<App client={createClient({ applyRepairPreview: applyPreview })} />);

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(await screen.findByRole("button", { name: "Configure repair" }));
    await user.click(await screen.findByRole("radio", { name: "Source gathering" }));
    await user.click(screen.getByRole("button", { name: "Generate preview" }));
    await user.click(await screen.findByRole("button", { name: "Cancel preview" }));

    expect(applyPreview).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Repair preview")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Configure repair" })).toBeInTheDocument();
  });

  it("applies a preview, refreshes public read models, and clears stale Construct cards", async () => {
    const user = userEvent.setup();
    const getRun = vi
      .fn<() => Promise<RunResponse>>()
      .mockResolvedValueOnce(run)
      .mockResolvedValue(runAfterApply);
    const getSpl = vi
      .fn<() => Promise<SplResponse>>()
      .mockResolvedValueOnce(spl)
      .mockResolvedValue(splAfterApply);
    const listConstructs = vi
      .fn<() => Promise<ConstructListResponse>>()
      .mockResolvedValueOnce(constructs)
      .mockResolvedValue(constructsAfterApply);
    const listIssues = vi
      .fn<() => Promise<IssueListResponse>>()
      .mockResolvedValueOnce(issues)
      .mockResolvedValue(issuesAfterApply);
    const getSplDocument = vi
      .fn<() => Promise<SplDocumentResponse>>()
      .mockResolvedValueOnce(splDocument)
      .mockResolvedValue({
        run_id: "demo",
        snapshot_id: "snap-demo",
        overlay_version: 1,
        revision_token: "demo:snap-demo:1",
        projection_status: "projection_unavailable",
        projection_fidelity: "partial",
        nodes: [],
      });
    const applyPreview = vi.fn(async () => repairApplyResult);
    render(
      <App
        client={createClient({
          getRun,
          getSpl,
          getSplDocument,
          listConstructs,
          listIssues,
          applyRepairPreview: applyPreview,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(await screen.findByRole("button", { name: "Configure repair" }));
    await user.click(await screen.findByRole("radio", { name: "Source gathering" }));
    await user.click(screen.getByRole("button", { name: "Generate preview" }));
    await user.click(await screen.findByRole("button", { name: "Apply repair" }));

    expect(applyPreview).toHaveBeenCalledWith("demo", "directive-1", "preview-1");
    expect(await screen.findByLabelText("Repair verification result")).toHaveTextContent("LaneB");
    expect(screen.getByText("Patched projection unavailable")).toBeInTheDocument();
    expect(screen.getByText("No SPL structure")).toBeInTheDocument();
    expect(screen.queryByText("MainWorker")).not.toBeInTheDocument();
    expect(screen.getAllByText("demo:snap-demo:1").length).toBeGreaterThanOrEqual(2);
    expect(getRun).toHaveBeenCalledTimes(2);
    expect(getSpl).toHaveBeenCalledTimes(2);
    expect(listConstructs).not.toHaveBeenCalled();
    expect(listIssues).toHaveBeenCalledTimes(2);
  });

  it("fails closed when the interaction contains an unsupported field", async () => {
    const user = userEvent.setup();
    const unsupported: RepairInteractionResponse = {
      ...repairInteraction,
      fields: [
        ...repairInteraction.fields,
        {
          field_id: "placement_ref",
          label: "Placement anchor",
          input_type: "reference_select",
          required: false,
          description: null,
          value: null,
          options: [],
          ref_role: "placement_anchor",
          object_schema_id: null,
          fact_schema_id: null,
        },
      ],
    };
    const submitDirective = vi.fn(async () => ({
      input_readiness: "input_complete",
      directive_id: "directive-1",
      errors: [],
    }));
    render(
      <App
        client={createClient({
          getRepairInteraction: async () => unsupported,
          submitRepairDirective: submitDirective,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(await screen.findByRole("button", { name: "Configure repair" }));

    expect(await screen.findByText("Unexpected repair fields: placement_ref.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate preview" })).not.toBeInTheDocument();
    expect(submitDirective).not.toHaveBeenCalled();
  });

  it("maps a stale revision interaction error without constructing a repair form", async () => {
    const user = userEvent.setup();
    render(
      <App
        client={createClient({
          getRepairInteraction: async () => {
            throw new ApiError(409, {
              error: {
                code: "stale_revision",
                message: "revision token is stale",
                details: {},
              },
            });
          },
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));
    await user.click(await screen.findByRole("button", { name: "Configure repair" }));

    expect(
      await screen.findByText("revision token is stale (stale_revision)"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate preview" })).not.toBeInTheDocument();
  });

  it("shows projection_unavailable as unsupported_in_mvp without stale cards", async () => {
    const unavailableRun = { ...run, projection_status: "projection_unavailable", construct_count: 0 };
    const unavailableSpl: SplResponse = {
      ...spl,
      projection_status: "projection_unavailable",
      rendered_spl: null,
      spl_cards: [],
      message: "Patched SPL projection is unavailable in this MVP build.",
    };
    const unavailableConstructs: ConstructListResponse = {
      ...constructs,
      projection_status: "projection_unavailable",
      constructs: [],
      message: "Patched Construct projection is unavailable in this MVP build.",
    };
    const emptyIssues: IssueListResponse = { ...issues, summary: [], sections: [] };
    const user = userEvent.setup();
    render(
      <App
        client={createClient({
          createRunFromSnapshot: async () => unavailableRun,
          getRun: async () => unavailableRun,
          getSpl: async () => unavailableSpl,
          getSplDocument: async () => ({
            run_id: "demo",
            snapshot_id: "snap-demo",
            overlay_version: 0,
            revision_token: "demo:snap-demo:0",
            projection_status: "projection_unavailable",
            projection_fidelity: "partial",
            nodes: [],
          }),
          listConstructs: async () => unavailableConstructs,
          listIssues: async () => emptyIssues,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));

    expect(await screen.findByText("Patched SPL projection is unavailable in this MVP build."))
      .toBeInTheDocument();
    expect(screen.getByText("No SPL structure")).toBeInTheDocument();
    expect(screen.queryByText("MainWorker")).not.toBeInTheDocument();
  });

  it("renders the stable API error state", async () => {
    const user = userEvent.setup();
    render(
      <App
        client={createClient({
          createRunFromSnapshot: async () => {
            throw new Error("Snapshot not found");
          },
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Load snapshot" }));

    expect(await screen.findByText("Run bootstrap failed")).toBeInTheDocument();
    expect(screen.getByText("Snapshot not found")).toBeInTheDocument();
  });
});
