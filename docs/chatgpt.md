# Flowlines in ChatGPT and Codex

The public distribution target is one **Flowlines** plugin with the hosted MCP
server and four shared analysis skills. Publish it through OpenAI's **With MCP**
submission flow to the universal Plugins Directory shared by ChatGPT and Codex.
The production server is `https://api.flowlines.ai/mcp`.

This repository prepares the submission. A merge does not publish the plugin,
install it for users, or migrate existing installations. OpenAI review and
publication are separate steps. No public listing or automatic installation
sync has been verified yet.

## Intended customer setup

After the public plugin is approved and published, customers should find
**Flowlines** in the Plugins Directory, install it, and connect their Flowlines
account when prompted. They should use that same listing in supported ChatGPT
and Codex surfaces. Developer mode, a personal app ID, and workspace marketplace
import are authoring and testing mechanisms, not the intended public setup.

One public listing does not establish that a single install or OAuth grant
automatically propagates to every device or CLI environment. Run the installation
checks below before describing the experience as "install once".

The initial public bundle contains:

- `flowlines-weekly-review`
- `flowlines-release-check`
- `flowlines-investigate-session`
- `flowlines-cohort-builder`

These skills use hosted tools and shared resources. Repository instrumentation,
local telemetry setup, and local diagnostics remain available through the
existing desktop marketplace. That marketplace and its `.mcp.json` integration
are preserved for existing Claude Code and Codex users.

## Prepare the public submission

From the repository root:

```sh
python3 scripts/build_public_submission.py --output dist/openai
```

Use Python 3.9 or newer and a new output directory. The build creates:

```text
dist/openai/
  flowlines/
    .codex-plugin/plugin.json
    assets/logo.png
    skills/
    LICENSE
  flowlines.zip
  openai-submission.md
  chatgpt.md
```

The archive contains the listing and skills portion of the submission. It
contains no `.app.json`, personal app ID, desktop MCP declaration, or marketplace.
It is not a connected plugin installer on its own. In the **same With MCP draft**,
submit the production MCP URL, configure OAuth, and add the skills and listing
assets. Do not create a second skills-only listing.

Use the [submission worksheet and review cases](openai-submission.md). The portal
must accept the uploaded skills, pass its scans, and bind the MCP tools before
the complete plugin can be verified. Rebuild after changes to the source skills
or version; the build always reads the existing `plugins/flowlines` source.

Offline checks:

```sh
python3 -m unittest discover -s scripts -p 'test_public_submission.py'
scripts/validate_plugins.sh
```

The CLI check installs the skills portion in a temporary validation marketplace
and confirms that it registers no desktop MCP server. This validates the local
package shape, not portal acceptance or the final connected public plugin.

## Test the MCP connection during development

Personal Plus and Pro accounts can use Developer mode without a workspace-admin
menu. Enable **Settings → Security and login → Developer mode**. In ChatGPT's
Plugins page, use the plus button to create a connection to the production URL
with OAuth. Complete sign-in, then start a fresh web chat and select
**+ → Developer mode → Flowlines**.

Ask it to use `get_workspace`, choose a namespace from the returned data, and
call `get_context` for that namespace. Inspect both tool calls. The maintainer
reported successful OAuth and this live query test on 2026-09-08. This result
verifies the direct MCP connection, not the submitted skill bundle or install
synchronization.

## Verify the complete public plugin

Use the same account and workspace throughout the following checks. Record the
canonical plugin ID, package version, client version, and date. The first pass
needs a clean test account or environment without the custom-marketplace plugin.

| Check | Evidence to record |
| --- | --- |
| Install Flowlines in ChatGPT web and complete OAuth | Public listing ID, install steps, and successful `get_workspace` / `get_context` calls. |
| Open ChatGPT desktop Chat/Work, then Codex in the desktop app | Whether Flowlines is already enabled; each additional install or sign-in action required; successful tool calls. |
| Open a fresh Codex CLI session signed in to the same account | Availability of the same plugin, additional setup required, and successful tool calls. |
| Select each of the four skills | Correct skill selection, resource access, and expected workflow output from the review cases. |
| Disconnect the service or use an account without access | Sign-in request or access error, with no invented or cross-account data. |
| Upgrade an existing custom-marketplace user | Any duplicate listing or MCP server, which integration handles calls, and explicit migration steps if needed. |

Keep unsupported surfaces and any extra install/authentication steps visible in
customer instructions. Do not claim automatic migration or "install once" until
these checks pass. Record only test results, not private workspace payloads.

## OAuth compatibility follow-up

On 2026-09-08, the public gateway returned unauthenticated `401` responses with
`x-amzn-remapped-www-authenticate` instead of `WWW-Authenticate`. The personal
Developer mode test still succeeded. [FLO-178](https://linear.app/flowline/issue/FLO-178/preserve-the-mcp-oauth-challenge-header-through-the-public-gateway)
tracks the separate header fix and external smoke checks; no infrastructure
fix is included here.

## References

- [Plugin architecture and the shared directory](https://developers.openai.com/plugins/concepts/plugins)
- [Public submission](https://developers.openai.com/plugins/deploy/submission)
- [Move an existing remote MCP plugin into one submission](https://developers.openai.com/plugins/guides/submit-claude-plugin)
- [Developer mode](https://developers.openai.com/api/docs/guides/developer-mode)
