# Usage Prompt Debug Scripts

These scripts call the real LLM for one stage at a time using the
`examples/usage.py` raw text scenario.

Each `stageN_usage_prompt.py` file exposes:

- `EXPECTED_INPUT`
- `EXPECTED_OUTPUT`

When run, the script executes only that stage, then prints:

- expected output
- actual LLM output parsed by the stage
- unified diff from expected to actual

Run one stage from the repository root:

```powershell
python examples\prompt_debug\stage7_usage_prompt.py
```

The scripts read `.env` from the repository root. Set `OPENAI_API_KEY` there or
in the shell environment before running.

The canonical expected IR data is shared with prompt unit fixtures through
`tests/fixtures/usage_prompt_expectations.py`, so the standalone scripts and
unit fixtures do not drift apart.
