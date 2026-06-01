# Worker Handoff Structured Unpack - Technical Implementation Details

## Problem Statement

When a multi-output `INVOKE_WORKER` handoff step is normalized by Stage 9.5 into a structured response, the ExecutableElementGate must recognize this transformation and validate both the producer and its dependent unpack steps together. Previously, the gate would:

1. Block the producer (outputs didn't match handoff bindings after normalization)
2. Allow unpack steps through (they had blanket exemption)
3. Result in orphaned unpack commands in final SPL

## Solution Architecture

### Phase 1: Handoff Output Matching Enhancement

**Location:** `src/nl2spl/pipeline/executable_gate.py:_handoff_outputs_match()`

The gate now recognizes two valid forms of handoff output matching:

#### Form 1: Direct Match (Original)
```python
step.outputs == expected_outputs
# Example: ["out_a", "out_b", "out_c"]
```

#### Form 2: Structured Response (New)
```python
len(step.outputs) == 1
step.outputs[0] == aggregation["result_name"]
aggregation["original_outputs"] == expected_outputs
aggregation["type_name"] exists
# Example: outputs=["handoff_xyz_response_structured"]
#          original_outputs=["out_a", "out_b", "out_c"]
```

**Implementation:**
```python
def _handoff_outputs_match(
    self,
    step: StepIR,
    expected_outputs: list[str],
) -> bool:
    # Try direct match first
    if list(step.outputs) == expected_outputs:
        return True

    # Check for structured aggregation
    aggregation = step.metadata.get("structured_aggregation")
    if not isinstance(aggregation, dict):
        return False

    # Validate structured response contract
    result_name = aggregation.get("result_name")
    if not result_name or len(step.outputs) != 1 or step.outputs[0] != result_name:
        return False

    # Must have type_name
    if not aggregation.get("type_name"):
        return False

    # Original outputs must match expected
    original_outputs = aggregation.get("original_outputs") or []
    return list(original_outputs) == expected_outputs
```

**Why This Works:**
- Preserves backward compatibility (direct match still works)
- Validates structured response has proper metadata
- Ensures original_outputs match handoff contract
- Requires type_name to be generated (prevents incomplete normalization)

### Phase 2: Two-Pass Unpack Filtering

**Location:** `src/nl2spl/pipeline/executable_gate.py:_filter_steps()`

The gate now processes steps in two passes to handle producer-consumer dependencies:

#### Pass 1: Filter Non-Unpack Steps
```python
unpack_steps: list[StepIR] = []

for step in steps:
    origin = self.classify_origin(step)
    if origin == "compiler_synthetic" and step.metadata.get("origin") == "compiler_unpack":
        unpack_steps.append(step)
        continue
    
    # Normal renderability check
    ok, reason = self.is_renderable(...)
    # Record in renderable_infos or blocked_infos
```

**Result:** Build `renderable_step_ids` set containing all non-unpack steps that passed validation.

#### Pass 2: Filter Unpack Steps with Strong Binding
```python
renderable_step_ids = {info.step_id for info in renderable_infos}
renderable_step_by_id = {s.step_id: s for s in steps if s.step_id in renderable_step_ids}

for step in unpack_steps:
    source_step_id = step.metadata.get("structured_source_step_id")
    structured_result = step.metadata.get("structured_result")
    unpacked_output = step.metadata.get("unpacked_output")
    
    # Validation chain (see below)
```

### Phase 3: Strong Binding Validation

Each compiler_unpack step must pass ALL of these checks:

#### Check 1: Metadata Presence
```python
if not source_step_id:
    reason = "compiler_unpack missing structured_source_step_id"
elif not structured_result:
    reason = "compiler_unpack missing structured_result"
elif not unpacked_output:
    reason = "compiler_unpack missing unpacked_output"
```

**Purpose:** Ensure normalizer created complete metadata.

#### Check 2: Producer Renderability
```python
elif source_step_id not in renderable_step_ids:
    reason = "compiler_unpack source step is not renderable"
```

**Purpose:** Prevent orphaned unpacks when producer is blocked.

#### Check 3: Producer Existence
```python
else:
    producer = renderable_step_by_id.get(source_step_id)
    if not producer:
        reason = f"compiler_unpack source step '{source_step_id}' not found"
```

**Purpose:** Ensure producer actually exists in the step list.

#### Check 4: Structured Result in Producer Outputs
```python
elif structured_result not in producer.outputs:
    reason = (
        f"compiler_unpack structured_result '{structured_result}' "
        f"not in producer outputs {producer.outputs}"
    )
```

**Purpose:** Validate unpack references the actual structured variable produced.

#### Check 5: Input Binding
```python
elif step.inputs != [structured_result]:
    reason = (
        f"compiler_unpack inputs {step.inputs} do not match "
        f"structured_result [{structured_result}]"
    )
```

**Purpose:** Ensure unpack reads from the correct structured variable.

#### Check 6: Output Binding
```python
elif len(step.outputs) != 1 or step.outputs[0] != unpacked_output:
    reason = (
        f"compiler_unpack output {step.outputs} does not match "
        f"unpacked_output [{unpacked_output}]"
    )
```

**Purpose:** Ensure unpack produces exactly one output matching metadata.

#### Check 7: Original Outputs Membership
```python
else:
    aggregation = producer.metadata.get("structured_aggregation")
    if not isinstance(aggregation, dict):
        reason = (
            f"compiler_unpack producer '{source_step_id}' "
            f"missing structured_aggregation metadata"
        )
    else:
        original_outputs = aggregation.get("original_outputs", [])
        if unpacked_output not in original_outputs:
            reason = (
                f"compiler_unpack output '{unpacked_output}' "
                f"not in producer original_outputs {original_outputs}"
            )
        else:
            ok = True
            reason = None
```

**Purpose:** Ensure unpack extracts a field that was actually in the original multi-output contract.

## Data Flow Example

### Input: Multi-Output Handoff Step
```python
StepIR(
    step_id="st_invoke",
    command_type="INVOKE_WORKER",
    handoff_id="handoff_generate_draft",
    outputs=["draft", "evidence", "assumptions", "status"],
    metadata={}
)
```

### After Stage 9.5 Normalization
```python
# Producer (modified)
StepIR(
    step_id="st_invoke",
    command_type="INVOKE_WORKER",
    handoff_id="handoff_generate_draft",
    outputs=["handoff_generate_draft_response_structured"],
    metadata={
        "structured_aggregation": {
            "result_name": "handoff_generate_draft_response_structured",
            "original_outputs": ["draft", "evidence", "assumptions", "status"],
            "type_name": "handoff_generate_draft_response_structured_type",
        },
        "handoff_output_bindings": [...]
    }
)

# Unpack steps (new)
StepIR(
    step_id="st_synthetic_1",
    command_type="GENERAL_COMMAND",
    text="Extract draft from handoff_generate_draft_response_structured",
    inputs=["handoff_generate_draft_response_structured"],
    outputs=["draft"],
    metadata={
        "origin": "compiler_unpack",
        "structured_source_step_id": "st_invoke",
        "structured_result": "handoff_generate_draft_response_structured",
        "unpacked_output": "draft",
    }
)
# ... 3 more unpack steps for evidence, assumptions, status
```

### Gate Processing

#### Pass 1: Validate Producer
```
1. Classify origin: "handoff_generated" (has handoff_id)
2. Check handoff contract:
   - handoff exists ✓
   - mode is "invoke" ✓
   - to_worker exists ✓
   - integration_ref matches ✓
   - inputs match ✓
   - outputs match via _handoff_outputs_match() ✓
     (recognizes structured response)
3. Result: RENDERABLE
4. Add to renderable_step_ids
```

#### Pass 2: Validate Unpack Steps
```
For each unpack step:
1. Check metadata presence ✓
2. Check source_step_id in renderable_step_ids ✓
3. Get producer from renderable_step_by_id ✓
4. Check structured_result in producer.outputs ✓
5. Check step.inputs == [structured_result] ✓
6. Check step.outputs == [unpacked_output] ✓
7. Check unpacked_output in producer.original_outputs ✓
8. Result: RENDERABLE
```

### Final Output
All 5 steps (1 producer + 4 unpacks) pass through gate and render to SPL:
```spl
INVOKE Worker_generate_draft ... RESPONSE handoff_generate_draft_response_structured SET
COMMAND Extract draft from handoff_generate_draft_response_structured ... RESULT draft SET
COMMAND Extract evidence from handoff_generate_draft_response_structured ... RESULT evidence SET
COMMAND Extract assumptions from handoff_generate_draft_response_structured ... RESULT assumptions SET
COMMAND Extract status from handoff_generate_draft_response_structured ... RESULT status SET
```

## Error Cases Handled

### Case 1: Producer Blocked, Unpacks Orphaned
**Before Fix:**
- Producer blocked (output mismatch)
- Unpacks allowed through (blanket exemption)
- Result: Orphaned extract commands

**After Fix:**
- Producer blocked (output mismatch)
- Unpacks blocked (source step not renderable)
- Result: No orphaned commands

### Case 2: Malformed Unpack Metadata
**Scenario:** Unpack missing `structured_result`

**Result:**
- Blocked with reason: "compiler_unpack missing structured_result"
- Diagnostic emitted: `missing_output_producer`

### Case 3: Unpack References Wrong Producer
**Scenario:** Unpack `structured_source_step_id` points to different step

**Result:**
- Blocked with reason: "structured_result not in producer outputs"
- Prevents cross-contamination between different structured results

### Case 4: Unpack Extracts Non-Existent Field
**Scenario:** Unpack `unpacked_output` not in producer's `original_outputs`

**Result:**
- Blocked with reason: "not in producer original_outputs"
- Prevents fabrication of outputs not in original contract

## Performance Considerations

### Time Complexity
- **Pass 1:** O(n) where n = number of steps
- **Pass 2:** O(m) where m = number of unpack steps
- **Total:** O(n + m) = O(n) since m ≤ n

### Space Complexity
- `renderable_step_ids`: O(n)
- `renderable_step_by_id`: O(n)
- `unpack_steps`: O(m)
- **Total:** O(n)

### Optimization Notes
- Two-pass approach is necessary for correctness (can't validate unpacks until producers are classified)
- Dictionary lookup for producer is O(1)
- No redundant iterations or nested loops

## Testing Strategy

### Unit Tests
1. **Direct handoff match** - Validates backward compatibility
2. **Structured handoff match** - Validates new recognition logic
3. **Unpack with renderable producer** - Validates happy path
4. **Unpack with blocked producer** - Validates dependency blocking
5. **Unpack with wrong structured_result** - Validates output binding
6. **Unpack with wrong inputs** - Validates input binding
7. **Unpack with wrong output** - Validates original_outputs membership

### Integration Tests
- Full normalizer → gate → renderer flow
- Multi-worker scenarios with child workers
- Exception flow preservation
- Diagnostic emission

### Regression Tests
- `test_internal_comms_2_regression()` - Validates the original bug is fixed
- `test_unpack_strong_binding_validation()` - Validates all edge cases

## Maintenance Notes

### Adding New Metadata Fields
If normalizer adds new metadata to structured aggregation:
1. Update `_handoff_outputs_match()` if it affects contract validation
2. Update Pass 2 validation if it affects unpack binding
3. Add test case for new validation

### Extending to Other Command Types
If other command types (CALL_API, etc.) need structured aggregation:
1. Normalizer must add same metadata structure
2. Gate validation will automatically apply
3. Add command-type-specific tests

### Debugging Tips
- Check `StepRenderInfo.render_block_reason` for why steps are blocked
- Check `CompileDiagnostic` with kind="missing_output_producer" for unpack issues
- Verify `structured_aggregation` metadata is complete in normalizer output
- Verify `handoff_output_bindings` metadata is present for handoff steps
