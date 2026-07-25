import type { RepairApplyResponse } from "../api";
import { StateView, StatusBadge } from "./StateView";

export function VerificationPanel({ result }: { result: RepairApplyResponse }) {
  const verification = result.verification;
  const acceptanceStatus = verification.accepted === true
    ? "accepted"
    : verification.accepted === false
      ? "not_accepted"
      : "unknown";
  const issueCount = result.issues.sections.reduce(
    (total, section) => total + section.items.length,
    0,
  );
  return (
    <section className="panel verification-panel" aria-label="Repair verification result">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Applied repair result</p>
          <h2>Verification</h2>
        </div>
        <div className="detail-badges">
          <StatusBadge value={result.status} />
          <StatusBadge value={acceptanceStatus} />
        </div>
      </div>
      <dl className="verification-grid">
        <div>
          <dt>Lane</dt>
          <dd>{verification.lane ?? "—"}</dd>
        </div>
        <div>
          <dt>Overlay</dt>
          <dd>{result.overlay_version}</dd>
        </div>
        <div>
          <dt>Projection</dt>
          <dd>
            <StatusBadge value={result.projection_status} />
          </dd>
        </div>
        <div>
          <dt>Updated issues</dt>
          <dd>{issueCount}</dd>
        </div>
        <div className="verification-grid__wide">
          <dt>Revision token</dt>
          <dd>
            <code>{result.revision_token}</code>
          </dd>
        </div>
      </dl>
      {verification.failure_reasons.length > 0 ? (
        <StateView title="Verification failure reasons" tone="error" compact>
          <ul className="compact-list">
            {verification.failure_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </StateView>
      ) : (
        <StateView title="No verification failure reason" tone="success" compact />
      )}
      <div className="verification-diagnostics">
        <div>
          <strong>Resolved diagnostics</strong>
          <span>{verification.resolved_diagnostic_ids.length}</span>
        </div>
        <div>
          <strong>New blocking diagnostics</strong>
          <span>{verification.new_blocking_diagnostic_ids.length}</span>
        </div>
      </div>
      {result.projection_status === "projection_unavailable" ? (
        <StateView title="Patched projection unavailable" tone="warning" compact>
          Repair was applied and verification completed. The MVP intentionally cleared initial SPL
          cards because no public patched read-model is available.
        </StateView>
      ) : null}
    </section>
  );
}
