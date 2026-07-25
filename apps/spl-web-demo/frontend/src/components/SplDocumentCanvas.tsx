import { useEffect, useRef, useState } from "react";
import type { ProvenanceResponse, SplDocumentNode } from "../api";

interface SplDocumentCanvasProps {
  nodes: SplDocumentNode[];
  selectedConstructRef: string | null;
  onSelect(ref: string): void;
  provenanceRevisionKey: string;
  loadProvenance(ref: string): Promise<ProvenanceResponse>;
}

interface TreeNode {
  node: SplDocumentNode;
  children: TreeNode[];
}

interface TooltipState {
  status: "loading" | "ready" | "error";
  texts: string[];
}

function buildTree(nodes: SplDocumentNode[]): TreeNode[] {
  const nodeMap = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  // Initialize Map
  nodes.forEach((node) => {
    if (nodeMap.has(node.node_ref)) {
      throw new Error(`duplicate SPL document node_ref: ${node.node_ref}`);
    }
    nodeMap.set(node.node_ref, { node, children: [] });
  });

  // Link Parents and Children
  nodes.forEach((node) => {
    const current = nodeMap.get(node.node_ref)!;
    if (node.parent_node_ref) {
      const parent = nodeMap.get(node.parent_node_ref);
      if (!parent) {
        throw new Error(
          `missing SPL document parent ${node.parent_node_ref} for ${node.node_ref}`,
        );
      }
      parent.children.push(current);
    } else {
      roots.push(current);
    }
  });

  // Sort children by order
  nodes.forEach((node) => {
    const current = nodeMap.get(node.node_ref)!;
    current.children.sort((a, b) => a.node.order - b.node.order);
  });

  // Sort roots by order
  roots.sort((a, b) => a.node.order - b.node.order);

  return roots;
}

export function SplDocumentCanvas({
  nodes,
  selectedConstructRef,
  provenanceRevisionKey,
  loadProvenance,
  onSelect,
}: SplDocumentCanvasProps) {
  const treeRoots = buildTree(nodes);
  const [hoveredRef, setHoveredRef] = useState<string | null>(null);
  const [tooltipByRef, setTooltipByRef] = useState<Record<string, TooltipState>>({});
  const tooltipGeneration = useRef(0);
  const pendingTooltipRefs = useRef(new Set<string>());

  useEffect(() => {
    tooltipGeneration.current += 1;
    pendingTooltipRefs.current.clear();
    setHoveredRef(null);
    setTooltipByRef({});
  }, [provenanceRevisionKey]);

  const requestTooltip = async (constructRef: string) => {
    if (tooltipByRef[constructRef] || pendingTooltipRefs.current.has(constructRef)) {
      return;
    }
    const generation = tooltipGeneration.current;
    pendingTooltipRefs.current.add(constructRef);
    setTooltipByRef((current) => ({
      ...current,
      [constructRef]: { status: "loading", texts: [] },
    }));
    try {
      const response = await loadProvenance(constructRef);
      if (generation !== tooltipGeneration.current) {
        return;
      }
      setTooltipByRef((current) => ({
        ...current,
        [constructRef]: {
          status: "ready",
          texts: provenanceTexts(response),
        },
      }));
    } catch {
      if (generation !== tooltipGeneration.current) {
        return;
      }
      setTooltipByRef((current) => ({
        ...current,
        [constructRef]: { status: "error", texts: [] },
      }));
    } finally {
      if (generation === tooltipGeneration.current) {
        pendingTooltipRefs.current.delete(constructRef);
      }
    }
  };

  return (
    <div className="spl-canvas">
      <div className="spl-canvas__tree">
        {treeRoots.map((root) => (
          <DocumentNodeView
            key={root.node.node_ref}
            treeNode={root}
            selectedConstructRef={selectedConstructRef}
            onSelect={onSelect}
            hoveredRef={hoveredRef}
            onHover={(constructRef) => {
              setHoveredRef(constructRef);
              void requestTooltip(constructRef);
            }}
            onLeave={() => setHoveredRef(null)}
          />
        ))}
      </div>
      {hoveredRef ? <ProvenanceTooltip state={tooltipByRef[hoveredRef]} /> : null}
    </div>
  );
}

function ProvenanceTooltip({ state }: { state: TooltipState | undefined }) {
  return (
    <div className="provenance-tooltip provenance-tooltip--canvas" role="tooltip">
      <strong>Provenance</strong>
      {!state || state.status === "loading" ? <p>Loading source text...</p> : null}
      {state?.status === "error" ? <p>Source text unavailable.</p> : null}
      {state?.status === "ready" && state.texts.length === 0 ? (
        <p>No concrete source text.</p>
      ) : null}
      {state?.status === "ready"
        ? state.texts.map((value) => <blockquote key={value}>{value}</blockquote>)
        : null}
    </div>
  );
}

function provenanceTexts(response: ProvenanceResponse): string[] {
  const provenance = response.provenance;
  if (!provenance) {
    return [];
  }
  const texts = [
    ...provenance.spans.map((span) => span.text),
    ...provenance.traces.flatMap((trace) =>
      trace.repair?.user_text ? [trace.repair.user_text] : [],
    ),
  ];
  return [...new Set(texts.filter(Boolean))].slice(0, 3);
}

interface DocumentNodeViewProps {
  treeNode: TreeNode;
  selectedConstructRef: string | null;
  onSelect(ref: string): void;
  hoveredRef: string | null;
  onHover(ref: string): void;
  onLeave(): void;
}

function DocumentNodeView({
  treeNode,
  selectedConstructRef,
  onSelect,
  hoveredRef,
  onHover,
  onLeave,
}: DocumentNodeViewProps) {
  const { node, children } = treeNode;
  const [collapsed, setCollapsed] = useState(false);

  const selected = Boolean(
    node.construct_ref && node.construct_ref === selectedConstructRef,
  );

  const handleClick = (e: React.MouseEvent) => {
    if (node.construct_ref) {
      e.stopPropagation();
      onSelect(node.construct_ref);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      if (node.construct_ref) {
        e.preventDefault();
        onSelect(node.construct_ref);
      }
    }
  };

  if (node.node_kind === "section") {
    return (
      <div className={`doc-section doc-section--${node.node_type.toLowerCase()}`}>
        <div
          className="doc-section-header"
          onClick={() => setCollapsed(!collapsed)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setCollapsed(!collapsed);
            }
          }}
        >
          <span className="doc-section-toggle">{collapsed ? "▶" : "▼"}</span>
          <span className="doc-section-tag">{node.node_type}</span>
          <span className="doc-section-title">{node.title}</span>
          {node.summary && <span className="doc-section-summary">({node.summary})</span>}
        </div>
        {!collapsed && children.length > 0 && (
          <div className="doc-section-body">
            {children.map((child) => (
              <DocumentNodeView
                key={child.node.node_ref}
                treeNode={child}
                selectedConstructRef={selectedConstructRef}
                onSelect={onSelect}
                hoveredRef={hoveredRef}
                onHover={onHover}
                onLeave={onLeave}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // Under construct node_kind:
  // Render specific layout depending on node_type
  let content = null;

  if (node.node_type === "PERSONA") {
    content = (
      <div
        className={`construct-worker-card ${selected ? "construct-command-row--selected" : ""}`}
        style={{ borderTopColor: "#8b5cf6", borderColor: "#ddd6fe" }}
      >
        <div
          className="card-header"
          style={{ background: "#f5f3ff", borderBottomColor: "#ede9fe" }}
          onClick={handleClick}
          role="button"
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
          onMouseLeave={onLeave}
        >
          <div className="card-header-left">
            <span
              className="card-header-tag tag-flow"
              style={{ background: "#ede9fe", color: "#6d28d9" }}
            >
              Persona
            </span>
            <h3>{node.title}</h3>
          </div>
          <div className="card-header-actions">
            <span
              className="construct-subtype"
              style={{
                background: "#ede9fe",
                color: "#6d28d9",
                padding: "0.2rem 0.5rem",
                borderRadius: "4px",
                fontSize: "0.7rem",
                fontWeight: "bold",
              }}
            >
              Profile
            </span>
          </div>
        </div>
        <div className="card-body" style={{ padding: "1rem 1.25rem" }}>
          <p className="description" style={{ margin: 0, fontSize: "0.85rem", color: "#4b5563" }}>
            {node.summary}
          </p>
          {children.length > 0 && (
            <div
              className="card-body-nested"
              style={{
                marginTop: "1rem",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
              }}
            >
              {children.map((child) => (
                <DocumentNodeView
                  key={child.node.node_ref}
                  treeNode={child}
                  selectedConstructRef={selectedConstructRef}
                  onSelect={onSelect}
                  hoveredRef={hoveredRef}
                  onHover={onHover}
                  onLeave={onLeave}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  } else if (node.node_type === "CONSTRAINT") {
    const text = stringValue(node.attributes.text) ?? "";

    content = (
      <div
        className={`construct-flow-card ${selected ? "construct-command-row--selected" : ""}`}
        style={{ borderTopColor: "#f59e0b", borderColor: "#fef3c7", cursor: "pointer", marginBottom: "1rem" }}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
        onMouseLeave={onLeave}
      >
        <div className="card-header" style={{ background: "#fffbeb", borderBottomColor: "#fef3c7" }}>
          <div className="card-header-left">
            <span
              className="card-header-tag tag-exception"
              style={{ background: "#fef3c7", color: "#d97706" }}
            >
              Constraint
            </span>
            <h3>{node.title}</h3>
          </div>
        </div>
        <div className="card-body" style={{ padding: "1rem 1.25rem", fontSize: "0.78rem", color: "#4b5563" }}>
          <p style={{ margin: 0, lineHeight: "1.4" }}>{text}</p>
        </div>
      </div>
    );
  } else if (node.node_type === "WORKER") {
    content = (
      <div
        className={`construct-worker-card ${selected ? "construct-command-row--selected" : ""}`}
      >
        <div
          className="card-header"
          onClick={handleClick}
          role="button"
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
          onMouseLeave={onLeave}
        >
          <div className="card-header-left">
            <span className="card-header-tag tag-worker">Worker</span>
            <h3>{node.title}</h3>
          </div>
          <div className="card-header-actions">
            <span className="construct-subtype" style={{ marginRight: "8px" }}>
              {node.attributes.worker_kind === "main" ? "MAIN" : "CHILD"}
            </span>
          </div>
        </div>
        {node.summary && (
          <div className="card-header-desc" style={{ padding: "0.5rem 1.25rem 0", margin: 0 }}>
            {node.summary}
          </div>
        )}
        {children.length > 0 && (
          <div className="card-body">
            {children.map((child) => (
              <DocumentNodeView
                key={child.node.node_ref}
                treeNode={child}
                selectedConstructRef={selectedConstructRef}
                onSelect={onSelect}
                hoveredRef={hoveredRef}
                onHover={onHover}
                onLeave={onLeave}
              />
            ))}
          </div>
        )}
      </div>
    );
  } else if (node.node_type === "FLOW" || node.node_type === "EXCEPTION_FLOW") {
    const isException = node.node_type === "EXCEPTION_FLOW";
    const flowKind = stringValue(node.attributes.flow_kind) ?? "";

    return (
      <div className={isException ? "construct-exception-flow-card" : "construct-flow-card"}>
        <div
          className="card-header"
          onClick={handleClick}
          role="button"
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
          onMouseLeave={onLeave}
        >
          <div className="card-header-left">
            <span className={`card-header-tag ${isException ? "tag-exception" : "tag-flow"}`}>
              {isException ? "Exception Flow" : "Flow"}
            </span>
            <h3>{isException ? "EXCEPTION FLOW" : `FLOW · ${flowKind.toUpperCase()}`}</h3>
            <span className="card-header-desc" style={{ marginLeft: "0.5rem" }}>{node.title}</span>
          </div>
        </div>
        {children.length > 0 && (
          <div className="card-body">
            {children.map((child) => (
              <DocumentNodeView
                key={child.node.node_ref}
                treeNode={child}
                selectedConstructRef={selectedConstructRef}
                onSelect={onSelect}
                hoveredRef={hoveredRef}
                onHover={onHover}
                onLeave={onLeave}
              />
            ))}
          </div>
        )}
      </div>
    );
  } else if (node.node_type === "BLOCK") {
    const blockType = stringValue(node.attributes.block_type) ?? "Block";
    return (
      <div className="construct-block-card">
        <div
          className="card-header"
          onClick={handleClick}
          role="button"
          tabIndex={0}
          onKeyDown={handleKeyDown}
          onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
          onMouseLeave={onLeave}
        >
          <div className="card-header-left">
            <span className="card-header-tag tag-block">Block</span>
            <h3>BLOCK · {blockType.toUpperCase()}</h3>
            <span className="card-header-desc" style={{ marginLeft: "0.5rem" }}>{node.title}</span>
          </div>
        </div>
        {children.length > 0 && (
          <div className="card-body">
            {children.map((child) => (
              <DocumentNodeView
                key={child.node.node_ref}
                treeNode={child}
                selectedConstructRef={selectedConstructRef}
                onSelect={onSelect}
                hoveredRef={hoveredRef}
                onHover={onHover}
                onLeave={onLeave}
              />
            ))}
          </div>
        )}
      </div>
    );
  } else if (node.node_type === "COMMAND") {
    const isUnplaced = node.status === "review_only";
    const commandResult = readCommandResult(node.attributes.result);
    return (
      <div
        className={`construct-command-row ${
          selected ? "construct-command-row--selected" : ""
        } ${isUnplaced ? "construct-command-row--unplaced" : ""}`}
        onClick={handleClick}
        onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
        onMouseLeave={onLeave}
        role="button"
        tabIndex={0}
        onKeyDown={handleKeyDown}
      >
        <div className="command-row-left">
          <span className="command-drag-handle">⋮⋮</span>
          <span className="command-row-tag">COMMAND</span>
          <span className="command-row-text">{node.title}</span>
        </div>
        {commandResult && (
          <div className="command-row-right">
            {commandResult.map((r) => (
              <span key={r.name} className="command-result-badge">
                {r.keyword} {r.name}: {r.data_type} {r.assignment}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  } else if (node.node_type === "OUTPUT") {
    // REQUIRED_OUTPUT outputs

    return (
      <div
        className={`construct-command-row ${selected ? "construct-command-row--selected" : ""}`}
        onClick={handleClick}
        onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
        onMouseLeave={onLeave}
        role="button"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        style={{ borderLeft: "4px solid #10b981" }}
      >
        <div className="command-row-left">
          <span className="command-row-tag" style={{ background: "#e6f4ea", color: "#137333" }}>OUTPUT</span>
          <span className="command-row-text">{node.title}</span>
          {node.summary && <span className="command-row-desc">({node.summary})</span>}
        </div>
      </div>
    );
  } else {
    // Default leaf construct card row rendering (CONCEPT, VARIABLE, FILE, API, API_FUNCTION, INPUT, etc.)
    content = (
      <>
        <div
          className={`construct-command-row ${selected ? "construct-command-row--selected" : ""}`}
          onClick={handleClick}
          onMouseEnter={() => node.construct_ref && onHover(node.construct_ref)}
          onMouseLeave={onLeave}
          role="button"
          tabIndex={0}
          onKeyDown={handleKeyDown}
        >
          <div className="command-row-left">
            <span className="command-row-tag">{node.node_type}</span>
            <span className="command-row-text">{node.title}</span>
            {node.summary && <span className="command-row-desc">- {node.summary}</span>}
          </div>
        </div>
        {children.length > 0 && (
          <div
            className="card-body-nested"
            style={{ paddingLeft: "1.5rem", marginTop: "0.25rem", width: "100%" }}
          >
            {children.map((child) => (
              <DocumentNodeView
                key={child.node.node_ref}
                treeNode={child}
                selectedConstructRef={selectedConstructRef}
                onSelect={onSelect}
                hoveredRef={hoveredRef}
                onHover={onHover}
                onLeave={onLeave}
              />
            ))}
          </div>
        )}
      </>
    );
  }

  return <div className="doc-node-wrapper">{content}</div>;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

interface CommandResultItem {
  keyword: string;
  name: string;
  data_type: string;
  assignment: string;
}

function readCommandResult(value: unknown): CommandResultItem[] | null {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  const items: CommandResultItem[] = [];
  for (const entry of value) {
    if (
      entry &&
      typeof entry === "object" &&
      typeof (entry as Record<string, unknown>).keyword === "string" &&
      typeof (entry as Record<string, unknown>).name === "string"
    ) {
      items.push({
        keyword: (entry as Record<string, string>).keyword,
        name: (entry as Record<string, string>).name,
        data_type: (entry as Record<string, string>).data_type || "text",
        assignment: (entry as Record<string, string>).assignment || "SET",
      });
    }
  }
  return items.length > 0 ? items : null;
}
