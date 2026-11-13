# 0006 — LLM provider abstraction with two providers

**Status:** Accepted (2026-11-13)

**Decision.** All model calls go through an `LLMProvider` interface with structured output,
validation and per-call metadata recording. Ship OpenAI first plus a second provider to keep the
abstraction honest. Organisations can disable AI; deterministic template explanations are the
fallback.

**Consequences.** No module imports a vendor SDK directly. Evaluation suites run against each
configured provider.
