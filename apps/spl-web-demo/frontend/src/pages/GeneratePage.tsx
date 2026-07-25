import { useState, FormEvent } from "react";
import type { SplWebDemoClient } from "../api";
import { formatError } from "../components/StateView";

const DEFAULT_REQUIREMENT = `Create an internal newsletter coordinator agent.

The agent must collect approved internal updates, verify that sourced claims have evidence, match
the approved newsletter template, and produce a newsletter draft. If required information is
missing, it must ask for the missing information before finalizing the draft. The final output is
the newsletter draft.`;

const DEFAULT_SNAPSHOT_PATH = "examples/output/demo/spl_editing_snapshot.json";

interface GeneratePageProps {
  client: SplWebDemoClient;
  onNavigate(path: string): void;
}

export default function GeneratePage({ client, onNavigate }: GeneratePageProps) {
  const [rawText, setRawText] = useState(DEFAULT_REQUIREMENT);
  const [language, setLanguage] = useState("zh-CN");
  const [snapshotPath, setSnapshotPath] = useState(DEFAULT_SNAPSHOT_PATH);

  const [loading, setLoading] = useState(false);
  const [activeAction, setActiveAction] = useState<"compile" | "snapshot" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCompile = async (e: FormEvent) => {
    e.preventDefault();
    if (!rawText.trim() || loading) return;

    setLoading(true);
    setActiveAction("compile");
    setError(null);

    try {
      const res = await client.createRun({
        raw_text: rawText,
        language: language,
        precompute_issue_explanations: false,
      });
      onNavigate(`/runs/${res.run_id}`);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  };

  const handleLoadSnapshot = async (e: FormEvent) => {
    e.preventDefault();
    if (!snapshotPath.trim() || loading) return;

    setLoading(true);
    setActiveAction("snapshot");
    setError(null);

    try {
      const res = await client.createRunFromSnapshot(snapshotPath);
      onNavigate(`/runs/${res.run_id}`);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  };

  return (
    <div className="generate-page">
      <header className="generate-page__header">
        <h1>SPL Web Demo</h1>
      </header>
      <main className="generate-page__content">
        <div className="generate-card">
          <h2>Generate SPL</h2>
          <p className="generate-card__subtitle">
            Input natural-language requirements to compile them into structural SPL compiler IR.
          </p>

          <form onSubmit={handleCompile} className="compile-form">
            <div className="form-group">
              <label htmlFor="raw-requirement" className="form-label">
                Initial requirement
              </label>
              <textarea
                id="raw-requirement"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={10}
                placeholder="Enter natural language requirements..."
                disabled={loading}
              />
            </div>

            <div className="form-row">
              <div className="form-group select-group">
                <label htmlFor="language" className="form-label">
                  Language
                </label>
                <select
                  id="language"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  disabled={loading}
                >
                  <option value="zh-CN">Chinese (zh-CN)</option>
                  <option value="en-US">English (en-US)</option>
                </select>
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading || !rawText.trim()}
              >
                {activeAction === "compile" ? "Compiling..." : "Generate SPL"}
              </button>
            </div>
          </form>

          {error && (
            <div className="generate-error alert alert-error">
              <h4>Run bootstrap failed</h4>
              <p>{error}</p>
            </div>
          )}

          <details className="snapshot-bootstrap">
            <summary>Local debug: load canonical snapshot</summary>
            <form onSubmit={handleLoadSnapshot} className="snapshot-form">
              <div className="form-group">
                <label htmlFor="snapshot-path" className="form-label">
                  Snapshot path
                </label>
                <div className="input-group">
                  <input
                    id="snapshot-path"
                    value={snapshotPath}
                    onChange={(e) => setSnapshotPath(e.target.value)}
                    placeholder="examples/output/demo/spl_editing_snapshot.json"
                    disabled={loading}
                  />
                  <button
                    type="submit"
                    className="btn btn-secondary"
                    disabled={loading || !snapshotPath.trim()}
                  >
                    {activeAction === "snapshot" ? "Loading..." : "Load snapshot"}
                  </button>
                </div>
              </div>
            </form>
          </details>
        </div>
      </main>
    </div>
  );
}
