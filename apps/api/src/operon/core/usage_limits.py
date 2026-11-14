"""Rate limits for costly or abusable operations (security review, Phase 7).

Authentication limits live with identity. These protect model spend and shared resources:
the assistant, agent runs, detection runs, explanation rewrites, purchase requests and exports.
"""

from fastapi import Request

from operon.core.rate_limit import Limit, RateLimiter

SLOW_DOWN = "You're doing that too often. Try again in a few minutes."

ASSISTANT_PER_USER = Limit("assistant_user", 20, 5 * 60, SLOW_DOWN)
ASSISTANT_PER_ORG = Limit(
    "assistant_org", 500, 24 * 3600, "Your organisation reached today's assistant limit."
)
AGENT_RUNS_PER_ORG = Limit("agent_runs_org", 12, 3600, "The agent can be started 12 times an hour.")
DETECTION_RUNS_PER_ORG = Limit("detection_org", 30, 3600, SLOW_DOWN)
EXPLAIN_PER_ORG = Limit("explain_org", 60, 3600, SLOW_DOWN)
PURCHASE_REQUESTS_PER_USER = Limit("purchase_requests_user", 30, 3600, SLOW_DOWN)
EXPORTS_PER_ORG = Limit("exports_org", 5, 24 * 3600, "Exports are limited to five a day.")


async def hit(request: Request, limit: Limit, subject: object) -> None:
    await RateLimiter(request.app.state.redis).hit(limit, str(subject))
