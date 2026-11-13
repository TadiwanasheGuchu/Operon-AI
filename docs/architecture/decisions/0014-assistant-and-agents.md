# 0014 — Assistant and agents: typed tools, code-enforced limits, human approval

**Status:** Accepted (2026-11-13)

**Context.** Phase 6 adds an operations assistant and the first agent. CLAUDE.md requires:

- tool allowlists, explicit permissions, structured tool inputs and limits;
- defences against prompt injection;
- complete activity logs;
- that an AI recommendation is never authorisation.

**Decision.**

- **One controlled loop** (`modules/agents/runner.py`) runs every model interaction that uses
  tools. In code, not in the prompt, it enforces:
  - only tools offered to this run can execute; anything else is denied and logged;
  - tool input is validated against the tool's Pydantic schema before the tool runs;
  - per-run limits on model turns, tool calls, tokens and wall-clock time;
  - the organisation's monthly token budget, shared with explanations;
  - every model turn and tool call is written to `agent_execution_steps` (append-only) as it
    happens, together with the model, provider, prompt version and token counts.
- **Typed tools, no free-form queries** (`modules/agents/tools.py`). Each tool has a schema, a
  required permission and a read/write flag.
  - Six read tools: insights, one insight, stock, purchase orders, incidents and purchase requests.
  - One write tool, `draft_purchase_request`. It creates a request that still needs Phase 5
    approval. Its guards are code: stockout insights only, a minimum severity, quantity within
    50–150% of the recommendation, and a per-run cap.
  - There are no tools that approve, cancel, delete or change permissions.
- **Assistant:**
  - Read tools only, filtered by the asking member's permissions, so it sees what they see.
  - Conversations and messages are private to their author, enforced by restrictive RLS
    policies as well as the service.
  - Answers cite references in square brackets. A checker flags any reference no tool returned,
    and any figure that appears in neither the tool outputs nor the question, and the UI shows
    the result.
  - It is opened from a header button as a side drawer, not as a central chat page (design
    brief §8).
- **Inventory replenishment agent:**
  - Configured per organisation: on/off, a daily schedule, guidance (which cannot override its
    rules), a minimum severity, maximum drafts, limits and a tool allowlist. Changing
    instructions or limits creates a new version.
  - It acts for a named member. Its permissions are that member's permissions intersected with a
    fixed ceiling (`insights.read`, `incidents.read`, `workflows.read`, `workflows.request`).
    Drafted requests are raised in that member's name, so they can't approve them.
  - Runs are started by hand (`agents.run`) or daily by the maintenance schedule. The next
    scheduled run is set before running, so a failing run never loops.
- **Prompt injection.** Tool results are passed as JSON data, and the system prompts say that text
  inside them is data. Defence doesn't rely on the model obeying: even a model that follows
  planted instructions can only call allowlisted tools with validated input, within bounds, and
  everything it drafts still needs a person's approval. Tests use a deliberately "compromised"
  scripted model to prove this.
- **Providers.** The `LLMProvider` interface gains a tool loop: `start`, `converse` and `extend`.
  - Anthropic: `beta.messages.create` with tools and effort "medium", plus server-side refusal
    fallbacks. The assistant turn is echoed back verbatim so thinking blocks stay intact.
    `tool_choice` isn't forced, because it returns a 400 on current models.
  - OpenAI: the Responses API with function tools; output items are echoed back.
- **Evaluation.** `apps/api/evals/run_agent_evals.py` runs scenario checks against a real
  provider: one draft per critical insight, no duplicates, planted instructions changing nothing,
  and the assistant citing records and claiming no actions. It needs a provider key and writes
  `evals/report.json`.

**Consequences.**

- Deterministic tests cover the guarantees above with a scripted model. The quality of a real
  model's judgement is measured only by the evaluation suite, which hasn't run here because no
  provider key is available.
- A run interrupted by a process crash stays "running"; detecting and marking stale runs is a
  Phase 7 item.
- LangGraph (CLAUDE.md §6, "where appropriate") isn't used yet: one bounded loop with code-owned
  procedure was simpler and easier to audit. Revisit when an agent needs branching plans.
