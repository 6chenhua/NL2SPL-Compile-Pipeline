import type { FormEvent } from "react";

interface RunLoaderProps {
  rawText: string;
  snapshotPath: string;
  loading: boolean;
  activeAction: "compile" | "snapshot" | null;
  onRawTextChange(value: string): void;
  onSnapshotPathChange(value: string): void;
  onCompile(): void;
  onLoadSnapshot(): void;
}

export function RunLoader({
  rawText,
  snapshotPath,
  loading,
  activeAction,
  onRawTextChange,
  onSnapshotPathChange,
  onCompile,
  onLoadSnapshot,
}: RunLoaderProps) {
  const submitCompile = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onCompile();
  };
  const submitSnapshot = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onLoadSnapshot();
  };

  return (
    <div className="run-loader">
      <form className="run-loader__compile" onSubmit={submitCompile}>
        <label htmlFor="raw-requirement">
          <span className="field-label">Initial requirement</span>
          <span className="field-help">
            Compile natural-language requirements through the live NL2SPL pipeline.
          </span>
        </label>
        <textarea
          id="raw-requirement"
          name="rawRequirement"
          value={rawText}
          onChange={(event) => onRawTextChange(event.target.value)}
          rows={6}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !rawText.trim()}>
          {activeAction === "compile" ? "Compiling..." : "Generate SPL IR"}
        </button>
      </form>

      <details className="snapshot-bootstrap">
        <summary>Debug snapshot bootstrap</summary>
        <form className="run-loader__snapshot" onSubmit={submitSnapshot}>
          <label htmlFor="snapshot-path">
            <span className="field-label">Snapshot path</span>
            <span className="field-help">
              Load a canonical SPL Editing snapshot through the local debug endpoint.
            </span>
          </label>
          <div className="run-loader__controls">
            <input
              id="snapshot-path"
              name="snapshotPath"
              value={snapshotPath}
              onChange={(event) => onSnapshotPathChange(event.target.value)}
              placeholder="examples/output/demo/spl_editing_snapshot.json"
              autoComplete="off"
              disabled={loading}
            />
            <button type="submit" disabled={loading || !snapshotPath.trim()}>
              {activeAction === "snapshot" ? "Loading..." : "Load snapshot"}
            </button>
          </div>
        </form>
      </details>
    </div>
  );
}
