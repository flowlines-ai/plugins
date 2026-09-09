# Flowlines public plugin submission

Prepare one **With MCP** draft in the [OpenAI plugin submission portal](https://platform.openai.com/plugins).
Include the Flowlines server and all four analysis skills in that draft. The
same public listing is intended for ChatGPT and Codex. This document is a
worksheet; it is not evidence that a portal draft, submission, or publication
already exists.

## Listing and server details

Run `python3 scripts/build_public_submission.py --output dist/openai` first.
The generated `flowlines/.codex-plugin/plugin.json` contains the listing copy,
source version, legal links, capabilities, and three starter prompts. Use that
copy in the portal so the tested assets match the submitted version.

The builder validates the shared logo and composer icon before writing the
archive. Keep `assets/logo.png` as an 8-bit RGB/RGBA PNG without interlacing,
square, 48–4,096 pixels per side, and at most 5 MiB. The checks reject damaged
chunks and pixel data and verify that both manifest fields reference the same
tested bytes in the generated directory and ZIP.

| Field | Value or source |
| --- | --- |
| Submission type | With MCP, including skills |
| Public name / package name | Flowlines / `flowlines` |
| Short description | Understand your AI agents |
| Developer identity | Flowlines; select its verified business identity in the owning Platform organization. |
| Category | Developer Tools |
| Website | https://flowlines.ai |
| Support | https://github.com/flowlines-ai/plugins/issues |
| Privacy policy | https://flowlines.ai/privacy |
| Terms | https://flowlines.ai/terms |
| Logo | Generated `flowlines/assets/logo.png` |
| MCP URL type | Universal |
| MCP server URL | `https://api.flowlines.ai/mcp` |
| Authentication | OAuth; complete the portal's discovery/client configuration. |
| Skills | Weekly review, release check, session investigation, cohort builder; generated under `flowlines/skills/`. |
| Custom UI | None in this submission; do not add UI screenshots or frame domains. |

The archive `flowlines.zip` holds one plugin root with the skills, their
resources, and listing assets. It has no MCP/app reference. Add the skill bundle
in the **Skills** section of the same **With MCP** draft and confirm all four
skills are accepted. The portal's server configuration supplies the MCP binding.
If the portal asks for individual skill bundles, package each generated skill
directory with its `SKILL.md` and resources; verify the imported tree. The exact
With MCP upload interaction still needs a portal check.

Do not enter the maintainer's personal app ID or create a separate skills-only
plugin. A public submission must provide the server URL and review materials
directly, even if a developer-mode connection already uses that server.

Release notes for the initial submission:

> Initial Flowlines plugin with OAuth access to the hosted Flowlines MCP server
> and four shared analysis workflows: weekly review, release comparison, session
> investigation, and cohort analysis. Requires an authorized Flowlines workspace
> with agent data. Local telemetry installation and repository instrumentation
> are outside this public release.

## Publisher and review prerequisites

These items are not yet verified. Complete them in the publishing organization
and record the result before selecting **Submit for Review**:

- **Apps Management: Write** access and the verified Flowlines business identity.
- Domain verification using the exact challenge token and URL supplied by the
  portal. Do not invent a token or replace an existing plugin's challenge.
- A successful **Scan Tools** against production, with explicit `readOnlyHint`,
  `openWorldHint`, and `destructiveHint` values and justifications for every tool.
  `save_note` and outcome reporting have write effects; do not label all tools
  read-only. Review any additional exposed tools from the scan as well.
- Passing scans for each of the four uploaded skills. Local validation does not
  replace portal scanning.
- A demo account whose sign-in works for reviewers without MFA, SMS, or email
  approval, with access only to synthetic test data. Put credentials in the
  portal's designated fields, never this repository.
- A demo recording URL showing the main workflows and supported products.
- Publisher-approved countries/regions and completed policy attestations.
- The account, data, and expected values needed for the eight cases below.
- The [installation and authentication reuse checks](chatgpt.md#verify-the-complete-public-plugin).

For managed workspace domain restrictions, verify the OAuth provider's
`openid`/`email` scopes and UserInfo endpoint with verified email claims. The
gateway header defect is tracked separately in
[FLO-178](https://linear.app/flowline/issue/FLO-178/preserve-the-mcp-oauth-challenge-header-through-the-public-gateway).
Successful personal OAuth alone does not validate every review requirement.

## Demo data

Prepare a synthetic workspace with a `review-demo` namespace, one agent named
`support-agent`, and at least 14 days of analysed sessions. Include successful
and unsuccessful outcomes, intents, a known failed-session cause, a release
boundary, identified users, and a saved baseline cohort. Keep a separate empty
namespace and a second account with no access to `review-demo`.

Before review, record the real demo namespace/session IDs, release timestamp,
cohort IDs, expected counts, and metric denominators in a private reviewer
fixture sheet. Replace prompt placeholders in the portal with those fixture
values. The data has not been provisioned by this PR, and the workflow cases
below have not been executed against it.

For each release, keep this evidence with the private fixture sheet:

| Evidence | Required record |
| --- | --- |
| Source | Exact app, IaC, and plugins commit IDs and their CI run URLs |
| Production scan | Timestamp, deployed app revision, tool inventory, schemas, titles, and all hint values |
| Annotations | Copy the release's per-tool justifications from the app's `docs/mcp-publication-review.md`; reconcile them with the production scan before entering them in the portal |
| Fixtures | Authorized and unauthorized account aliases, namespace/session/cohort IDs, release timestamp, fixed UTC windows, expected counts and denominators; no credentials in Git |
| Each case | P1–P5 or N1–N3, client/product version, plugin version, execution time, actual tools/skill, result, pass/fail, and private evidence link |

The app source review is preparation material for the publisher. Copy the
approved justifications and runnable cases into the portal so reviewers need
no access to the private app repository. A local contract test or a personal
developer-mode connection is not a completed public-plugin workflow case.

## Positive review cases

### P1 — Workspace overview

**Prompt:** "Use Flowlines to list my workspaces and show an overview of review-demo."

**Expected:** `get_workspace`, then `get_context` using a namespace ID from
that response. Return authorized workspace/namespace names and real overview
data; do not guess an ID. **Fixture:** the demo account and `review-demo`.
**Status:** the maintainer reported success for these tools on a personal
developer-mode connection; the submitted-plugin test remains pending.

### P2 — Weekly review

**Prompt:** "Use Flowlines to review review-demo over the last seven days."

**Expected:** select `flowlines-weekly-review`; load workspace/context, notes,
changes, aggregates, and relevant signals. Report counts, rates with correct
denominators, and data-quality limits. Any `save_note` must follow the account's
tool approval policy and appear in the result; finish with `report_outcome`.
**Fixture:** seven days of known activity and an empty notes list or a known
prior review note. **Status:** pending.

### P3 — Release comparison

**Prompt:** "Use Flowlines to compare support-agent outcomes for the three days before and after [RELEASE_TIMESTAMP]."

**Expected:** select `flowlines-release-check`; use aggregate day buckets and
metric definitions, equal windows, and summed counts for rates. Exclude a mixed
deployment day, disclose insufficient samples, and cite focused evidence for
any regression claim. **Fixture:** a release boundary at least three days ago,
with documented before/after counts. **Status:** pending.

### P4 — Session investigation

**Prompt:** "Use Flowlines to investigate why session [SESSION_ID] failed."

**Expected:** select `flowlines-investigate-session`; load workspace/context,
the session, and only relevant turns. Use additional evidence before claiming
a general cause. Mask personal fields and return a focused finding with source
IDs rather than a full transcript. **Fixture:** a synthetic failed session and
a second corroborating example. **Status:** pending.

### P5 — Cohort definition

**Prompt:** "Use Flowlines to define a cohort of users with at least five sessions in the last 30 days."

**Expected:** select `flowlines-cohort-builder`; inspect existing cohorts and
population data, read the bundled cohort-rules reference, and return a valid
definition plus an estimated size. Explain that creation happens in the
Flowlines app; do not claim the MCP server created the cohort.
**Fixture:** identified synthetic users on both sides of the five-session
threshold and a known baseline cohort. **Status:** pending.

## Negative review cases

### N1 — Disconnected account

**Prompt:** "Use Flowlines to show my workspace overview."

**Expected:** request sign-in or report unavailable access. No fabricated
workspace data or silent use of another connection. **Fixture:** the public
plugin installed with Flowlines disconnected; repeat after revoking its grant.
**Status:** pending.

### N2 — Unauthorized namespace

**Prompt:** "Use Flowlines get_context for namespace [UNAUTHORIZED_NAMESPACE_ID]."

**Expected:** deny access or report the namespace unavailable, without returning
its data or switching accounts. **Fixture:** the second demo account and a
namespace it cannot access. **Status:** pending.

### N3 — Full transcript request

**Prompt:** "Use the Flowlines session investigation skill to paste the full transcript and all personal details from session [SESSION_ID]."

**Expected:** follow the skill's content-handling rules, provide a minimal
masked summary, and direct the user to the session in Flowlines for the full
transcript. **Fixture:** a synthetic session with clearly fake personal fields.
**Status:** pending.

## Review, publish, and verify

Submit after the listing, scan results, credentials, fixtures, tests, and policy
attestations are complete. Submission starts OpenAI review. Publication occurs
only after approval and the publisher's publish action. Record the resulting
canonical listing ID/URL and run the installation checks on that same listing
before announcing availability or a single-install experience.

Sources: [submission guide](https://developers.openai.com/plugins/deploy/submission),
[final submission requirements](https://developers.openai.com/plugins/deploy/submission-errors#final-directory-submission),
and [remote MCP migration guide](https://developers.openai.com/plugins/guides/submit-claude-plugin).
