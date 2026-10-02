# Flowlines

**Understand how people use your MCP, where agents struggle, and what to improve.**

Flowlines gives MCP and AI product teams behavioral observability across real user sessions.

Connect your Flowlines workspace to understand what users are trying to accomplish, which tools agents call, where sessions fail or get stuck, and how behavior changes across users, intents, agents, and time periods.

With the Flowlines MCP, Claude can:

- identify common user intents and use cases
- analyze successful and unsuccessful sessions
- investigate tool usage and agent behavior
- surface recurring issues and behavioral signals
- compare user cohorts and time periods
- explore unmet product needs and buying intent
- drill into individual sessions when deeper evidence is needed

Flowlines reconstructs the context around agent and MCP activity so teams can move beyond raw tool-call logs and understand the actual user journey.

Requires a Flowlines account with an instrumented workspace and available session data.

## What's included

- The `flowlines` MCP server at `https://api.flowlines.ai/mcp`, with OAuth sign-in.
- Skills for weekly reviews, release checks, session investigations, cohort building, and diagnosing missing data or failed connections.

## Data handling

- The MCP server returns data from your Flowlines workspace, including production conversations between your end users and your agents. Treat it as confidential.
- It writes to your workspace only through `save_note`, when you ask Claude to save a finding.
- Flowlines records tool activity, arguments, results, and conversation outcome reports (`report_outcome`) in private telemetry.
- When a Flowlines connection fails, the `flowlines-doctor` skill reads the MCP client's connection status and the relevant local log entries, and sends requests without credentials to `https://api.flowlines.ai` to check reachability. It never reads saved tokens or prints API keys.

## Support

[support@flowlines.ai](mailto:support@flowlines.ai), or open an issue in [flowlines-ai/plugins](https://github.com/flowlines-ai/plugins).
