import { useEffect, useState, useMemo, useRef } from "react";
import type {
  SplWebDemoClient,
  RunResponse,
  SplDocumentResponse,
  IssueListResponse,
  SplResponse,
  ProvenanceResponse,
  SpanResponse,
  IssueDetailResponse,
  RepairApplyResponse,
} from "../api";
import { SplDocumentCanvas } from "../components/SplDocumentCanvas";
import { RepairWorkspace } from "../components/RepairWorkspace";
import { VerificationPanel } from "../components/VerificationPanel";
import { StateView, StatusBadge, formatError } from "../components/StateView";



function firstIssueId(issues: IssueListResponse): string | null {
  for (const s of issues.sections) {
    if (s.items.length > 0) {
      return s.items[0].issue_id;
    }
  }
  return null;
}

interface SplWorkbenchPageProps {
  client: SplWebDemoClient;
  runId: string;
  onNavigate(path: string): void;
}

type InspectorMode = "construct" | "issue" | "none";
type ConstructTab = "Details" | "Provenance";
type ProblemTab = "all" | "editable" | "review_only";

export default function SplWorkbenchPage({ client, runId, onNavigate }: SplWorkbenchPageProps) {
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [loadError, setLoadError] = useState<string | null>(null);

  // Read models cached in component state
  const [run, setRun] = useState<RunResponse | null>(null);
  const [doc, setDoc] = useState<SplDocumentResponse | null>(null);
  const [issues, setIssues] = useState<IssueListResponse | null>(null);
  const [spl, setSpl] = useState<SplResponse | null>(null);

  // Inspector & selection states
  const [inspectorMode, setInspectorMode] = useState<InspectorMode>("none");
  const [selectedConstructRef, setSelectedConstructRef] = useState<string | null>(null);
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [constructTab, setConstructTab] = useState<ConstructTab>("Details");
  const [problemTab, setProblemTab] = useState<ProblemTab>("all");
  const [problemsCollapsed, setProblemsCollapsed] = useState(false);
  const [rawSplOpen, setRawSplOpen] = useState(false);

  // Sub-resource states
  const [provenance, setProvenance] = useState<ProvenanceResponse | null>(null);
  const [provenanceLoading, setProvenanceLoading] = useState(false);
  const [provenanceError, setProvenanceError] = useState<string | null>(null);

  const [span, setSpan] = useState<SpanResponse | null>(null);

  const [issueDetail, setIssueDetail] = useState<IssueDetailResponse | null>(null);

  const [explanationLoading, setExplanationLoading] = useState(false);

  const [lastApplyResult, setLastApplyResult] = useState<RepairApplyResponse | null>(null);

  // Sequences to prevent race conditions
  const provenanceSequence = useRef(0);
  const spanSequence = useRef(0);
  const issueSequence = useRef(0);
  const explanationSequence = useRef(0);

  // Hydrate all workspace read models
  const hydrate = async (silent = false) => {
    if (!silent) {
      setLoadState("loading");
      setLoadError(null);
    }
    try {
      const [runData, docData, issuesData, splData] = await Promise.all([
        client.getRun(runId),
        client.getSplDocument(runId),
        client.listIssues(runId),
        client.getSpl(runId),
      ]);

      setRun(runData);
      setDoc(docData);
      setIssues(issuesData);
      setSpl(splData);
      setLoadState("ready");

      if (!silent) {
        // Auto-select first construct
        const firstConstruct = docData.nodes.find((n) => n.node_kind === "construct");
        if (firstConstruct && firstConstruct.construct_ref) {
          selectConstruct(firstConstruct.construct_ref);
        }
        // Auto-select first issue
        const firstIssue = firstIssueId(issuesData);
        if (firstIssue) {
          selectIssue(firstIssue);
        }
      }
    } catch (err) {
      if (!silent) {
        setLoadError(formatError(err));
        setLoadState("error");
      }
    }
  };

  useEffect(() => {
    void hydrate();
  }, [runId]);

  // Selections
  const selectConstruct = (ref: string) => {
    setSelectedConstructRef(ref);
    setInspectorMode("construct");
    void fetchProvenance(ref);
  };

  const selectIssue = (issueId: string) => {
    setSelectedIssueId(issueId);
    setInspectorMode("issue");
    void fetchIssueDetail(issueId);
  };

  const fetchProvenance = async (constructRef: string) => {
    const seq = provenanceSequence.current + 1;
    provenanceSequence.current = seq;
    setProvenanceLoading(true);
    setProvenanceError(null);
    setProvenance(null);
    setSpan(null);

    try {
      const res = await client.getConstructProvenance(runId, constructRef);
      if (provenanceSequence.current === seq) {
        setProvenance(res);
      }
    } catch (err) {
      if (provenanceSequence.current === seq) {
        setProvenanceError(formatError(err));
      }
    } finally {
      if (provenanceSequence.current === seq) {
        setProvenanceLoading(false);
      }
    }
  };

  const selectSpan = async (spanId: string) => {
    const seq = spanSequence.current + 1;
    spanSequence.current = seq;
    setSpan(null);

    try {
      const res = await client.getSpan(runId, spanId);
      if (spanSequence.current === seq) {
        setSpan(res);
      }
    } catch (err) {
      // Span fetch error logged silently
      console.error(err);
    }
  };

  const fetchIssueDetail = async (issueId: string) => {
    const seq = issueSequence.current + 1;
    issueSequence.current = seq;
    setIssueDetail(null);

    try {
      const res = await client.getIssue(runId, issueId);
      if (issueSequence.current === seq) {
        setIssueDetail(res);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleRequestExplanation = async () => {
    if (!selectedIssueId) return;
    const seq = explanationSequence.current + 1;
    explanationSequence.current = seq;
    setExplanationLoading(true);

    try {
      const response = await client.triggerIssueExplanation(runId, selectedIssueId);
      if (explanationSequence.current === seq) {
        setIssueDetail((current) =>
          current?.issue.issue_id === selectedIssueId
            ? { ...current, explanation: response.explanation }
            : current,
        );
      }
    } catch (err) {
      console.error(err);
    } finally {
      if (explanationSequence.current === seq) {
        setExplanationLoading(false);
      }
    }
  };

  const handleRepairApplied = async (result: RepairApplyResponse) => {
    setLastApplyResult(result);
    try {
      // Re-hydrate the full workbench state
      const [runData, docData, issuesData, splData] = await Promise.all([
        client.getRun(runId),
        client.getSplDocument(runId),
        client.listIssues(runId),
        client.getSpl(runId),
      ]);

      setRun(runData);
      setDoc(docData);
      setIssues(issuesData);
      setSpl(splData);

      // Handle fail-closed clear if nodes are empty
      if (docData.nodes.length === 0) {
        setSelectedConstructRef(null);
        setProvenance(null);
        setSpan(null);
      } else {
        // Safe auto-reselect first construct
        const firstConstruct = docData.nodes.find((n) => n.node_kind === "construct");
        if (firstConstruct && firstConstruct.construct_ref) {
          selectConstruct(firstConstruct.construct_ref);
        }
      }

      // Safe auto-reselect first issue
      const firstIssue = firstIssueId(issuesData);
      if (firstIssue) {
        selectIssue(firstIssue);
      } else {
        setSelectedIssueId(null);
        setIssueDetail(null);
      }
    } catch (err) {
      console.error("Refresh after apply failed:", err);
    }
  };

  const selectedConstructNode = useMemo(() => {
    return doc?.nodes.find((n) => n.construct_ref === selectedConstructRef) ?? null;
  }, [doc, selectedConstructRef]);

  const selectedIssueCard = useMemo(() => {
    if (!selectedIssueId || !issues) return null;
    return issues.sections.flatMap((s) => s.items).find((i) => i.issue_id === selectedIssueId) ?? null;
  }, [issues, selectedIssueId]);

  const allIssuesList = useMemo(() => {
    if (!issues) return [];
    return issues.sections.flatMap((s) => s.items);
  }, [issues]);

  const filteredIssues = useMemo(() => {
    if (problemTab === "all") return allIssuesList;
    if (problemTab === "editable") {
      return allIssuesList.filter((i) => i.repairability === "editable");
    }
    return allIssuesList.filter((i) => i.repairability !== "editable");
  }, [allIssuesList, problemTab]);

  if (loadState === "loading") {
    return <StateView title="Hydrating workbench..." />;
  }

  if (loadState === "error") {
    return (
      <StateView title="Failed to load run record" tone="error">
        <p>{loadError}</p>
        <button type="button" className="btn btn-primary" onClick={() => onNavigate("/")} style={{ marginTop: "1rem" }}>
          Back to generation
        </button>
      </StateView>
    );
  }

  if (!run || !doc || !issues || !spl) {
    return <StateView title="Loading workspace data..." />;
  }

  const isFidelityPartial = doc.projection_fidelity === "partial";

  return (
    <div className="workbench-page">
      {/* 56px Header */}
      <header className="workbench-header">
        <div className="workbench-header__left">
          <button
            type="button"
            className="btn btn-link"
            onClick={() => onNavigate("/")}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
          >
            New generation
          </button>
          <span className="divider">|</span>
          <span className="file-display-name">{run.run_id}.spl</span>
          <span className="divider">|</span>
          <span className="metadata-badge text-muted">
            Rev: {run.overlay_version} | Status: <StatusBadge value={run.snapshot_status} /> |
            Fidelity:{" "}
            <span style={{ fontWeight: "bold" }}>{doc.projection_fidelity}</span>
          </span>
          <span className="divider">|</span>
          <span className="metadata-badge text-muted">
            Revision token: <code>{run.revision_token ?? "none"}</code>
          </span>
        </div>
        <div className="workbench-header__right">
          <button type="button" className="btn btn-secondary" onClick={() => void hydrate(true)}>
            Refresh
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => setRawSplOpen(true)}>
            Raw SPL
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="workbench-container">
        {/* Left/Center Canvas */}
        <main className="workbench-canvas">
          {isFidelityPartial && (
            <div className="alert alert-warning" style={{ margin: "1rem", borderRadius: "6px" }}>
              <h4>Projection fidelity degraded (partial)</h4>
              <p>Applied changes have not yet been compiled into full visual nodes.</p>
            </div>
          )}

          {run.projection_status !== "available" ? (
            <>
              <StateView title="unsupported_in_mvp" tone="warning">
                {spl.message ??
                  (run.overlay_version > 0
                    ? "The API cannot expose a current patched SPL read-model for this overlay."
                    : "Compilation produced SPL, but the structured snapshot projection is unavailable.")}
              </StateView>
              <StateView title="No SPL structure" compact>
                The API returned an empty structured projection for this run.
              </StateView>
            </>
          ) : doc.nodes.length === 0 ? (
            <StateView title="No SPL visual nodes projected">
              Projection read-model is unavailable for this compile state.
            </StateView>
          ) : (
            <SplDocumentCanvas
              nodes={doc.nodes}
              selectedConstructRef={selectedConstructRef}
              onSelect={selectConstruct}
              provenanceRevisionKey={`${run.run_id}:${run.revision_token ?? "none"}`}
              loadProvenance={(constructRef) =>
                client.getConstructProvenance(runId, constructRef)
              }
            />
          )}
        </main>

        {/* Right Inspector Panel */}
        <aside className="workbench-inspector" aria-label="Properties inspector">
          <div className="inspector-header">
            {inspectorMode === "construct" && selectedConstructNode && (
              <>
                <span className="eyebrow">{selectedConstructNode.node_type}</span>
                <h2>{selectedConstructNode.title}</h2>
                <div className="inspector-tabs">
                  <button
                    type="button"
                    className={`inspector-tab ${constructTab === "Details" ? "active" : ""}`}
                    onClick={() => setConstructTab("Details")}
                  >
                    Details
                  </button>
                  <button
                    type="button"
                    className={`inspector-tab ${constructTab === "Provenance" ? "active" : ""}`}
                    onClick={() => setConstructTab("Provenance")}
                  >
                    Provenance
                  </button>
                </div>
              </>
            )}

            {inspectorMode === "issue" && issueDetail && (
              <>
                <span className="eyebrow" style={{ color: "#ef4444" }}>
                  {(selectedIssueCard?.display_id ?? "")} · {(selectedIssueCard?.repairability ?? "")}
                </span>
                <h2>{issueDetail.issue.title}</h2>
              </>
            )}

            {inspectorMode === "none" && (
              <h2 style={{ fontSize: "1.1rem", color: "#64748b" }}>Properties Inspector</h2>
            )}
          </div>

          <div className="inspector-body">
            {inspectorMode === "construct" && selectedConstructNode && (
              <>
                {constructTab === "Details" && (
                  <div className="inspector-details">
                    <div className="property-row">
                      <dt>Status</dt>
                      <dd>
                        <StatusBadge value={selectedConstructNode.status} />
                      </dd>
                    </div>
                    {selectedConstructNode.summary && (
                      <div className="property-row">
                        <dt>Summary</dt>
                        <dd>{selectedConstructNode.summary}</dd>
                      </div>
                    )}
                    {Object.keys(selectedConstructNode.attributes).map((key) => (
                      <div className="property-row" key={key}>
                        <dt>{key}</dt>
                        <dd>{JSON.stringify(selectedConstructNode.attributes[key])}</dd>
                      </div>
                    ))}
                  </div>
                )}

                {constructTab === "Provenance" && (
                  <div className="inspector-provenance">
                    {provenanceLoading ? (
                      <p>Loading provenance...</p>
                    ) : provenanceError ? (
                      <p style={{ color: "red" }}>{provenanceError}</p>
                    ) : provenance?.provenance?.spans.length ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                        {provenance.provenance.spans.map((sp) => (
                          <div key={sp.span_id} className="provenance-span-box">
                            <blockquote>{sp.text}</blockquote>
                            <button
                              type="button"
                              className="btn btn-link btn-xs"
                              onClick={() => selectSpan(sp.span_id)}
                            >
                              Open source detail
                            </button>
                          </div>
                        ))}

                        {span && (
        <div className="span-detail-modal" aria-label="Source detail">
                            <h4>Span Details ({span.span.span_id})</h4>
                            {span.span.section_context && (
                              <p>
                                <strong>Context:</strong> {span.span.section_context}
                              </p>
                            )}
                            <blockquote>{span.span.text}</blockquote>
                            <button type="button" className="btn btn-secondary btn-xs" onClick={() => setSpan(null)}>
                              Close span
                            </button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-muted">No concrete source text is available.</p>
                    )}
                  </div>
                )}
              </>
            )}

            {inspectorMode === "issue" && issueDetail && (
              <div className="inspector-issue">
                <p className="issue-impact">{selectedIssueCard?.impact}</p>

                {/* AI explanation and repair form */}
                <div style={{ marginTop: "1rem" }}>
                  <h3>Cached Explanation</h3>
                  {issueDetail.explanation ? (
                    <>
                      {issueDetail.explanation.status === "ready" &&
                        issueDetail.explanation.value && (
                        <div
                          className="explanation-box"
                          style={{
                            background: "#f8fafc",
                            padding: "0.5rem",
                            borderRadius: "6px",
                            border: "1px solid #e2e8f0",
                          }}
                        >
                          <h4>{issueDetail.explanation.value.headline ?? "Issue explanation"}</h4>
                          <p>
                            <strong>Problem:</strong> {issueDetail.explanation.value.problem}
                          </p>
                          <p>
                            <strong>Impact:</strong> {issueDetail.explanation.value.impact}
                          </p>
                          <p>
                            <strong>Recommendation:</strong> {issueDetail.explanation.value.recommendation_reason}
                          </p>
                          {issueDetail.explanation.value.source_interpretation ? (
                            <p>
                              <strong>Source interpretation:</strong>{" "}
                              {issueDetail.explanation.value.source_interpretation}
                            </p>
                          ) : null}
                          {issueDetail.explanation.value.missing_information?.length ? (
                            <div>
                              <strong>Missing information:</strong>
                              <ul>
                                {issueDetail.explanation.value.missing_information.map((item) => (
                                  <li key={item}>{item}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          {issueDetail.explanation.value.questions?.length ? (
                            <div>
                              <strong>Questions:</strong>
                              <ul>
                                {issueDetail.explanation.value.questions.map((question) => (
                                  <li key={question}>{question}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          {issueDetail.explanation.value.generation_warning ? (
                            <StateView title="Generation warning" tone="warning" compact>
                              {issueDetail.explanation.value.generation_warning}
                            </StateView>
                          ) : null}
                        </div>
                      )}
                      
                      {issueDetail.explanation.status === "pending" && (
                        <StateView title="Explanation generation is pending" compact>
                          The API scheduled snapshot-level generation. Refresh this issue to read the cache again.
                        </StateView>
                      )}

                      {issueDetail.explanation.status === "error" && (
                        <StateView title="Explanation generation failed" tone="error" compact>
                          {issueDetail.explanation.error ?? "The cache contains an error state."}
                        </StateView>
                      )}

                      {issueDetail.explanation.status === "missing" && (
                        <div>
                          <StateView title="No cached explanation" compact>
                            Request asynchronous explanation generation for this issue.
                          </StateView>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={explanationLoading}
                            onClick={handleRequestExplanation}
                            style={{ marginTop: "0.5rem" }}
                          >
                            {explanationLoading ? "Requesting..." : "Request explanation"}
                          </button>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="text-muted">No cached explanation available.</p>
                  )}
                </div>

                {issueDetail.issue.available_repairs && issueDetail.issue.available_repairs.length > 0 && (
                  <div style={{ marginTop: "1.5rem" }}>
                    <h3>Repair Workspace</h3>
                    <RepairWorkspace
                      client={client}
                      runId={runId}
                      revisionToken={run.revision_token ?? ""}
                      issueId={selectedIssueId!}
                      options={issueDetail.issue.available_repairs}
                      onApplied={handleRepairApplied}
                    />
                  </div>
                )}
              </div>
            )}

            {inspectorMode === "none" && (
              <p className="text-muted" style={{ textAlign: "center", padding: "2rem 0" }}>
                Select a visual node from the canvas or an issue from the console.
              </p>
            )}
          </div>
        </aside>
      </div>

      {/* 220px Problems Dock */}
      <footer
        className={`problems-dock ${problemsCollapsed ? "collapsed" : ""}`}
        aria-labelledby="problems-heading"
      >
        <h2 className="sr-only" id="problems-heading">
          Problems
        </h2>
        <div className="problems-dock__header">
          <div className="problems-dock__tabs">
            <button
              type="button"
              className={`problems-dock__tab ${problemTab === "all" ? "active" : ""}`}
              onClick={() => setProblemTab("all")}
            >
              Problems ({allIssuesList.length})
            </button>
            <button
              type="button"
              className={`problems-dock__tab ${problemTab === "editable" ? "active" : ""}`}
              onClick={() => setProblemTab("editable")}
            >
              Editable ({allIssuesList.filter((i) => i.repairability === "editable").length})
            </button>
            <button
              type="button"
              className={`problems-dock__tab ${problemTab === "review_only" ? "active" : ""}`}
              onClick={() => setProblemTab("review_only")}
            >
              Review Only ({allIssuesList.filter((i) => i.repairability !== "editable").length})
            </button>
          </div>
          <button
            type="button"
            className="problems-dock__toggle"
            onClick={() => setProblemsCollapsed(!problemsCollapsed)}
          >
            {problemsCollapsed ? "Expand" : "Collapse"}
          </button>
        </div>

        {!problemsCollapsed && (
          <div className="problems-dock__body">
            {filteredIssues.length === 0 ? (
              <p className="no-issues">No IRS issues detected.</p>
            ) : (
              <table className="problems-table">
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Issue</th>
                    <th>Message</th>
                    <th>Category</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredIssues.map((issue) => {
                    const isSelected = selectedIssueId === issue.issue_id;
                    const severity = issue.repairability === "editable" ? "Error" : "Warning";
                    return (
                      <tr
                        key={issue.issue_id}
                        className={`problems-row ${isSelected ? "selected" : ""}`}
                        onClick={() => selectIssue(issue.issue_id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            selectIssue(issue.issue_id);
                          }
                        }}
                        tabIndex={0}
                        aria-label={`Open issue ${issue.title}`}
                        aria-selected={isSelected}
                      >
                        <td>
                          <span className={`severity-tag severity-tag--${severity.toLowerCase()}`}>
                            {severity}
                          </span>
                        </td>
                        <td>
                          <strong>{issue.display_id}</strong>
                        </td>
                        <td>{issue.impact}</td>
                        <td>{issue.category}</td>
                        <td>{issue.source_excerpt ?? "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}
      </footer>

      {/* Raw SPL Code Drawer */}
      {rawSplOpen && (
        <div className="raw-spl-drawer-overlay" onClick={() => setRawSplOpen(false)}>
          <div className="raw-spl-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <h2>Raw Rendered SPL</h2>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setRawSplOpen(false)}>
                Close
              </button>
            </div>
            <pre className="drawer-code">{spl.rendered_spl || "Rendered SPL text is not available."}</pre>
          </div>
        </div>
      )}

      {/* Last Apply Verification Panel */}
      {lastApplyResult && (
        <div className="apply-verification-overlay">
          <div className="apply-verification-dialog">
            <h3>Repair Applied Successfully</h3>
            <VerificationPanel result={lastApplyResult} />
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setLastApplyResult(null)}
              style={{ marginTop: "1.5rem" }}
            >
              Acknowledge
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
