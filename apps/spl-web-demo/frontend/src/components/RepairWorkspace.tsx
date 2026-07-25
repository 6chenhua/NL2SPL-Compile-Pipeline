import { useRef, useState } from "react";
import type {
  RepairApplyResponse,
  RepairDirectiveResponse,
  RepairInputField,
  RepairInteractionResponse,
  RepairOption,
  RepairPreviewResponse,
  SplWebDemoClient,
} from "../api";
import { formatError, StateView, StatusBadge } from "./StateView";

const SUPPORTED_OPTION_ID = "keep_in_main_flow";
const TASK_SELECTION_FIELD_ID = "task_selection";
const ADDITIONAL_INSTRUCTION_FIELD_ID = "additional_instruction";

type RepairStage =
  | "idle"
  | "loading_interaction"
  | "editing"
  | "submitting"
  | "preview_ready"
  | "applying";

interface RepairWorkspaceProps {
  client: SplWebDemoClient;
  runId: string;
  revisionToken: string;
  issueId: string;
  options: RepairOption[];
  onApplied(result: RepairApplyResponse): Promise<void>;
}

export function RepairWorkspace({
  client,
  runId,
  revisionToken,
  issueId,
  options,
  onApplied,
}: RepairWorkspaceProps) {
  const requestSequence = useRef(0);
  const [stage, setStage] = useState<RepairStage>("idle");
  const [interaction, setInteraction] = useState<RepairInteractionResponse | null>(null);
  const [taskSelection, setTaskSelection] = useState("");
  const [additionalInstruction, setAdditionalInstruction] = useState("");
  const [directive, setDirective] = useState<RepairDirectiveResponse | null>(null);
  const [preview, setPreview] = useState<RepairPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const supportedOption = options.find(
    (option) => option.option_id === SUPPORTED_OPTION_ID && option.availability === "available",
  );
  const unsupportedAvailableOptions = options.filter(
    (option) => option.availability === "available" && option.option_id !== SUPPORTED_OPTION_ID,
  );
  const support = interaction
    ? validateSupportedInteraction(interaction, issueId, revisionToken)
    : null;
  const busy = stage === "loading_interaction" || stage === "submitting" || stage === "applying";

  const selectRepair = async () => {
    if (!supportedOption || busy) {
      return;
    }
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setStage("loading_interaction");
    setInteraction(null);
    setDirective(null);
    setPreview(null);
    setTaskSelection("");
    setAdditionalInstruction("");
    setError(null);
    try {
      const response = await client.getRepairInteraction(
        runId,
        issueId,
        supportedOption.option_id,
        revisionToken,
      );
      if (requestSequence.current !== sequence) {
        return;
      }
      setInteraction(response);
      const taskField = response.fields.find(
        (field) => field.field_id === TASK_SELECTION_FIELD_ID,
      );
      const instructionField = response.fields.find(
        (field) => field.field_id === ADDITIONAL_INSTRUCTION_FIELD_ID,
      );
      setTaskSelection(initialChoiceValue(taskField));
      setAdditionalInstruction(
        typeof instructionField?.value === "string" ? instructionField.value : "",
      );
      setStage("editing");
    } catch (requestError) {
      if (requestSequence.current === sequence) {
        setStage("idle");
        setError(formatError(requestError));
      }
    }
  };

  const submitAndPreview = async () => {
    if (!interaction || !support?.supported || !taskSelection || busy) {
      return;
    }
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setStage("submitting");
    setDirective(null);
    setPreview(null);
    setError(null);
    try {
      const directiveResponse = await client.submitRepairDirective(runId, {
        issue_id: interaction.issue_id,
        strategy_id: interaction.strategy_id,
        option_id: interaction.option_id,
        contract_id: interaction.contract_id,
        contract_version: interaction.contract_version,
        revision_token: interaction.revision_token,
        field_values: { [TASK_SELECTION_FIELD_ID]: taskSelection },
        selected_ref_ids: {},
        new_fact_declarations: [],
        additional_instruction: additionalInstruction.trim() || null,
      });
      if (requestSequence.current !== sequence) {
        return;
      }
      setDirective(directiveResponse);
      if (!directiveResponse.directive_id) {
        setStage("editing");
        return;
      }
      const previewResponse = await client.previewRepairDirective(
        runId,
        directiveResponse.directive_id,
      );
      if (requestSequence.current !== sequence) {
        return;
      }
      setPreview(previewResponse);
      setStage("preview_ready");
    } catch (requestError) {
      if (requestSequence.current === sequence) {
        setStage("editing");
        setError(formatError(requestError));
      }
    }
  };

  const applyPreview = async () => {
    const directiveId = directive?.directive_id;
    const previewId = preview?.preview.preview_id;
    if (!directiveId || !previewId || stage !== "preview_ready") {
      return;
    }
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setStage("applying");
    setError(null);
    try {
      const result = await client.applyRepairPreview(runId, directiveId, previewId);
      if (requestSequence.current !== sequence) {
        return;
      }
      await onApplied(result);
    } catch (requestError) {
      if (requestSequence.current === sequence) {
        setStage("preview_ready");
        setError(formatError(requestError));
      }
    }
  };

  const cancel = () => {
    requestSequence.current += 1;
    setStage("idle");
    setInteraction(null);
    setTaskSelection("");
    setAdditionalInstruction("");
    setDirective(null);
    setPreview(null);
    setError(null);
  };

  return (
    <div className="detail-block repair-workspace">
      <div className="subsection-heading">
        <h3>Repair workflow</h3>
        <StatusBadge value={repairStageLabel(stage)} />
      </div>

      {error ? (
        <StateView title="Repair request failed" tone="error" compact>
          {error}
        </StateView>
      ) : null}

      {!supportedOption ? (
        <StateView title="unsupported_in_mvp" tone="warning" compact>
          This issue does not expose the verified worker delegation keep-in-main-flow option.
        </StateView>
      ) : null}

      {unsupportedAvailableOptions.length > 0 ? (
        <StateView title="Other repair options are display-only" tone="warning" compact>
          {unsupportedAvailableOptions.map((option) => option.label).join(", ")}. T5 does not infer
          forms for unverified repair contracts.
        </StateView>
      ) : null}

      {supportedOption && stage === "idle" ? (
        <article className="repair-option-card repair-option-card--actionable">
          <div className="trace-card__header">
            <strong>{supportedOption.label}</strong>
            <StatusBadge value={supportedOption.availability} />
          </div>
          <p>{supportedOption.description}</p>
          <button type="button" onClick={() => void selectRepair()}>
            Configure repair
          </button>
        </article>
      ) : null}

      {stage === "loading_interaction" ? (
        <StateView title="Loading repair interaction…" compact />
      ) : null}

      {interaction && support && !support.supported ? (
        <StateView title="unsupported_in_mvp" tone="warning">
          {support.reason}
        </StateView>
      ) : null}

      {interaction &&
      support?.supported &&
      stage !== "preview_ready" &&
      stage !== "applying" ? (
        <RepairForm
          interaction={interaction}
          taskSelection={taskSelection}
          additionalInstruction={additionalInstruction}
          disabled={busy}
          onTaskSelectionChange={setTaskSelection}
          onAdditionalInstructionChange={setAdditionalInstruction}
          onSubmit={() => void submitAndPreview()}
          onCancel={cancel}
        />
      ) : null}

      {directive?.errors.length ? (
        <StateView title="Directive input is not complete" tone="error" compact>
          <ul className="compact-list">
            {directive.errors.map((item, index) => (
              <li key={`${item.code}-${item.field_id ?? "global"}-${index}`}>
                {item.field_id ? `${item.field_id}: ` : ""}
                {item.message}
              </li>
            ))}
          </ul>
        </StateView>
      ) : null}

      {directive?.directive_id ? (
        <IdentityPanel
          directiveId={directive.directive_id}
          sessionId={preview?.session_id ?? null}
          suggestionId={preview?.suggestion_id ?? null}
          previewId={preview?.preview.preview_id ?? null}
        />
      ) : null}

      {preview ? <PreviewPanel preview={preview} /> : null}

      {preview?.preview.preview_id ? (
        <div className="button-row repair-confirmation-row">
          <button type="button" onClick={() => void applyPreview()} disabled={stage === "applying"}>
            {stage === "applying" ? "Applying…" : "Apply repair"}
          </button>
          <button
            type="button"
            className="button-secondary"
            onClick={cancel}
            disabled={stage === "applying"}
          >
            Cancel preview
          </button>
        </div>
      ) : null}
    </div>
  );
}

function RepairForm({
  interaction,
  taskSelection,
  additionalInstruction,
  disabled,
  onTaskSelectionChange,
  onAdditionalInstructionChange,
  onSubmit,
  onCancel,
}: {
  interaction: RepairInteractionResponse;
  taskSelection: string;
  additionalInstruction: string;
  disabled: boolean;
  onTaskSelectionChange(value: string): void;
  onAdditionalInstructionChange(value: string): void;
  onSubmit(): void;
  onCancel(): void;
}) {
  const taskField = interaction.fields.find(
    (field) => field.field_id === TASK_SELECTION_FIELD_ID,
  );
  const instructionField = interaction.fields.find(
    (field) => field.field_id === ADDITIONAL_INSTRUCTION_FIELD_ID,
  );
  if (!taskField) {
    return null;
  }
  return (
    <form
      className="repair-form"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <fieldset disabled={disabled}>
        <legend>{taskField.label}</legend>
        {taskField.description ? <p className="field-help">{taskField.description}</p> : null}
        <div className="choice-list">
          {taskField.options.map((option) => (
            <label key={option.option_id} className="choice-option">
              <input
                type="radio"
                name={TASK_SELECTION_FIELD_ID}
                value={option.value}
                checked={taskSelection === option.value}
                onChange={(event) => onTaskSelectionChange(event.target.value)}
                required={taskField.required}
              />
              <span>
                <strong>{option.label}</strong>
                {option.description ? <small>{option.description}</small> : null}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {instructionField ? (
        <label className="repair-text-field" htmlFor="repair-additional-instruction">
          <span className="field-label">{instructionField.label}</span>
          {instructionField.description ? (
            <span className="field-help">{instructionField.description}</span>
          ) : null}
          <textarea
            id="repair-additional-instruction"
            value={additionalInstruction}
            onChange={(event) => onAdditionalInstructionChange(event.target.value)}
            disabled={disabled}
            rows={4}
          />
        </label>
      ) : null}

      <div className="button-row">
        <button type="submit" disabled={disabled || !taskSelection}>
          {disabled ? "Generating preview…" : "Generate preview"}
        </button>
        <button type="button" className="button-secondary" onClick={onCancel} disabled={disabled}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function IdentityPanel({
  directiveId,
  sessionId,
  suggestionId,
  previewId,
}: {
  directiveId: string;
  sessionId: string | null;
  suggestionId: string | null;
  previewId: string | null;
}) {
  return (
    <dl className="repair-identity-list" aria-label="Repair identities">
      <div>
        <dt>Directive</dt>
        <dd>
          <code>{directiveId}</code>
        </dd>
      </div>
      <div>
        <dt>Session</dt>
        <dd>{sessionId ? <code>{sessionId}</code> : "—"}</dd>
      </div>
      <div>
        <dt>Suggestion</dt>
        <dd>{suggestionId ? <code>{suggestionId}</code> : "—"}</dd>
      </div>
      <div>
        <dt>Preview</dt>
        <dd>{previewId ? <code>{previewId}</code> : "—"}</dd>
      </div>
    </dl>
  );
}

function PreviewPanel({ preview }: { preview: RepairPreviewResponse }) {
  const summary = preview.preview.typed_artifact_summary;
  return (
    <article className="repair-preview" aria-label="Repair preview">
      <div className="subsection-heading">
        <h3>Repair preview</h3>
        <StatusBadge value={preview.preview.preview_id ? "ready" : "unavailable"} />
      </div>
      <dl className="detail-list">
        <div>
          <dt>Base snapshot</dt>
          <dd>{preview.preview.base_snapshot_id ?? "—"}</dd>
        </div>
        <div>
          <dt>Typed artifact</dt>
          <dd>{summary.type ?? "—"}</dd>
        </div>
        <div>
          <dt>Construct nodes</dt>
          <dd>{summary.construct_node_count}</dd>
        </div>
        <div>
          <dt>Construct roles</dt>
          <dd>{summary.construct_roles.join(", ") || "—"}</dd>
        </div>
        <div>
          <dt>Preview cards</dt>
          <dd>{preview.preview.spl_cards.length}</dd>
        </div>
      </dl>
      {preview.preview.spl_cards.length === 0 ? (
        <StateView title="Preview cards unavailable" tone="warning" compact>
          The backend exposed typed preview metadata but no stable preview Card projection.
        </StateView>
      ) : null}
      {preview.preview.rendered_preview ? (
        <details className="raw-spl-panel repair-preview-text">
          <summary>Rendered preview text</summary>
          <pre>{preview.preview.rendered_preview}</pre>
        </details>
      ) : (
        <StateView title="Rendered preview unavailable" compact />
      )}
    </article>
  );
}

function validateSupportedInteraction(
  interaction: RepairInteractionResponse,
  expectedIssueId: string,
  expectedRevisionToken: string,
): {
  supported: boolean;
  reason: string;
} {
  if (interaction.issue_id !== expectedIssueId) {
    return { supported: false, reason: "The interaction belongs to a different issue." };
  }
  if (interaction.revision_token !== expectedRevisionToken) {
    return { supported: false, reason: "The interaction revision is stale or mismatched." };
  }
  if (interaction.validation_errors.length > 0) {
    return { supported: false, reason: "The interaction contains backend validation errors." };
  }
  if (interaction.option_id !== SUPPORTED_OPTION_ID) {
    return { supported: false, reason: `Option ${interaction.option_id} is not enabled in T5.` };
  }
  if (interaction.availability !== "available") {
    return { supported: false, reason: "The selected interaction is not available." };
  }
  if (interaction.demo_availability === "unsupported_in_mvp") {
    return {
      supported: false,
      reason: `Unsupported input types: ${(interaction.unsupported_fields ?? []).join(", ")}.`,
    };
  }
  const allowed = new Set([TASK_SELECTION_FIELD_ID, ADDITIONAL_INSTRUCTION_FIELD_ID]);
  const unexpected = interaction.fields.filter((field) => !allowed.has(field.field_id));
  if (unexpected.length > 0) {
    return {
      supported: false,
      reason: `Unexpected repair fields: ${unexpected.map((field) => field.field_id).join(", ")}.`,
    };
  }
  const task = interaction.fields.find((field) => field.field_id === TASK_SELECTION_FIELD_ID);
  if (
    !task ||
    task.input_type !== "single_choice" ||
    !task.required ||
    task.options.length === 0 ||
    task.options.some((option) => !option.value.trim())
  ) {
    return {
      supported: false,
      reason: "The required task_selection single-choice contract is unavailable.",
    };
  }
  const instruction = interaction.fields.find(
    (field) => field.field_id === ADDITIONAL_INSTRUCTION_FIELD_ID,
  );
  if (
    instruction &&
    (instruction.input_type !== "long_text" || instruction.required)
  ) {
    return {
      supported: false,
      reason: "The additional_instruction field does not match the verified optional long-text contract.",
    };
  }
  return { supported: true, reason: "" };
}

function initialChoiceValue(field: RepairInputField | undefined): string {
  if (typeof field?.value !== "string") {
    return "";
  }
  return field.options.some((option) => option.value === field.value) ? field.value : "";
}

function repairStageLabel(stage: RepairStage): string {
  if (stage === "loading_interaction") {
    return "loading";
  }
  if (stage === "submitting") {
    return "generating_preview";
  }
  if (stage === "preview_ready") {
    return "preview_ready";
  }
  return stage;
}
