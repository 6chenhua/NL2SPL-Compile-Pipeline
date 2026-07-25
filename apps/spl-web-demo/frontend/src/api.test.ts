import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createSplWebDemoClient } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SPL Web Demo API client", () => {
  it("posts natural-language input with explanation precompute disabled", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createSplWebDemoClient().createRun({ raw_text: "Create a source-backed workflow." });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/demo/v1/runs");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      raw_text: "Create a source-backed workflow.",
      language: "zh-CN",
      precompute_issue_explanations: false,
    });
  });

  it("posts the snapshot path and preserves the public API prefix", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          run_id: "demo",
          editing_run_id: "demo",
          snapshot_id: "snap-demo",
          snapshot_status: "available",
          overlay_version: 0,
          revision_token: "demo:snap-demo:0",
          editing_available: true,
          projection_status: "available",
          construct_count: 27,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createSplWebDemoClient().createRunFromSnapshot("examples/output/demo/snapshot.json");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/demo/v1/runs/from-snapshot");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(
      JSON.stringify({ snapshot_path: "examples/output/demo/snapshot.json" }),
    );
  });

  it("reads the structured SPL document from the run-scoped route", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(
        JSON.stringify({
          run_id: "demo",
          snapshot_id: "snap-demo",
          overlay_version: 0,
          revision_token: "demo:snap-demo:0",
          projection_status: "available",
          projection_fidelity: "structured",
          nodes: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createSplWebDemoClient().getSplDocument("run/one");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/demo/v1/runs/run%2Fone/spl-document");
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("uses the frozen repair interaction, directive, preview, and apply routes", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createSplWebDemoClient();

    await client.getRepairInteraction(
      "demo",
      "issue/1",
      "keep_in_main_flow",
      "demo:snap:0",
    );
    await client.submitRepairDirective("demo", {
      issue_id: "issue/1",
      strategy_id: "strategy",
      option_id: "keep_in_main_flow",
      contract_id: "contract",
      contract_version: "1.0",
      revision_token: "demo:snap:0",
      field_values: { task_selection: "source gathering" },
      selected_ref_ids: {},
      new_fact_declarations: [],
      additional_instruction: null,
    });
    await client.previewRepairDirective("demo", "directive/1");
    await client.applyRepairPreview("demo", "directive/1", "preview/1");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/demo/v1/runs/demo/issues/issue%2F1/repair-options/keep_in_main_flow/interaction" +
        "?revision_token=demo%3Asnap%3A0",
    );
    expect(fetchMock.mock.calls[1][0]).toBe("/api/demo/v1/runs/demo/repair-directives");
    expect(fetchMock.mock.calls[1][1]?.body).toContain('"task_selection":"source gathering"');
    expect(fetchMock.mock.calls[2][0]).toBe(
      "/api/demo/v1/runs/demo/repair-directives/directive%2F1/preview",
    );
    expect(fetchMock.mock.calls[3][0]).toBe(
      "/api/demo/v1/runs/demo/repair-directives/directive%2F1/previews/preview%2F1/apply",
    );
    expect(fetchMock.mock.calls[3][1]?.body).toBe(JSON.stringify({ user_confirmation: true }));
  });

  it("maps the stable backend error envelope to ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            error: {
              code: "snapshot_not_found",
              message: "snapshot not found",
              details: {},
            },
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const request = createSplWebDemoClient().createRunFromSnapshot("missing.json");
    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      status: 404,
      code: "snapshot_not_found",
      message: "snapshot not found",
    });
  });
});
