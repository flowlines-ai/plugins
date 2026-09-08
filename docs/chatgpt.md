# Flowlines in ChatGPT

The desktop package at `plugins/flowlines` declares its server in `.mcp.json`.
ChatGPT workspace import marks a plugin with MCP server declarations as
**Desktop only**, including remote HTTPS servers. A ChatGPT web package must
reference a registered app through `.app.json` instead.

The build command below creates a separate `flowlines-chatgpt` package,
displayed as **Flowlines for ChatGPT**, with the Flowlines logo. This keeps it
distinct from the desktop `flowlines` plugin when both marketplaces are
installed in one workspace. It includes weekly reviews, release checks, session
investigations, and cohort analysis. Instrumentation, local telemetry setup,
and local diagnostics remain in the desktop package. The source skills and
existing marketplace are not modified.

## Import the workspace package

The committed marketplace at `chatgpt/` references Flowlines app
`asdk_app_6a9fca3f79688191832c5679c1691a0f`. Use it in a workspace that has
access to this connection. The app ID is a non-secret reference; each user
must still complete sign-in.

1. As a workspace admin, open **Admin → Plugins → Add → Import marketplace**.
2. Set **Source** to `https://github.com/flowlines-ai/plugins` and **Path** to
   `chatgpt`.
3. To test PR #8 before merge, set **Branch, tag, or commit** to
   `feat/flo-177-chatgpt-plugin`. After merge, use `main`.
4. Import, then enable **Flowlines for ChatGPT** and its required app for the
   intended roles.
5. Install the plugin and follow the fresh-chat checks under **Verify before
   release** below. A successful import does not verify live tool calls.

Reuse the existing connection when it is available in your workspace. Only
create another connection if your workspace needs its own app ID, then rebuild
the package with that ID as described below.

## Register and verify the connection

1. In ChatGPT, open **Settings → Security and login** and enable **Developer
   mode**, if your workspace permits it.
2. Open **Plugins**, select the plus button, and register Flowlines with the
   MCP server URL `https://api.flowlines.ai/mcp` and OAuth authentication.
3. Complete sign-in and consent. The server advertises dynamic client
   registration and PKCE S256. Use the exact callback URI shown by ChatGPT if
   configuring a predefined OAuth client.
4. Check that tools such as `get_workspace` and `get_context` are discovered.
5. Copy the app ID from the connection's management URL. A URL containing
   `plugin_asdk_app_...` represents the app ID `asdk_app_...`. The build accepts
   either identifier and removes the `plugin_` prefix; do not pass the full URL.
   Some settings URLs instead contain `connector=asdk_app_...`; copy that
   parameter's value.

The [packaging guide](https://developers.openai.com/plugins/build/plugins#create-and-test-a-plugin-locally-with-an-mcp-server)
describes the mapping with a `plugin_asdk_app...` ID, but the
[workspace import guide](https://learn.chatgpt.com/docs/enterprise/plugin-management#reference-an-existing-app-with-appjson)
explicitly requires the app ID without `plugin_`; this build follows the
workspace import guide.

The reference does not register an app, grant service access, or authenticate
other users. A workspace admin must enable the referenced app for the intended
roles. Each user must complete any required sign-in.

## Build the workspace package

From the repository root, set the variable to the real registered app ID:

```sh
read -r FLOWLINES_CHATGPT_APP_ID
python3 scripts/build_chatgpt_plugin.py \
  --app-id "$FLOWLINES_CHATGPT_APP_ID" \
  --output dist/chatgpt
```

Python 3.9 or newer is required. The output directory must not already exist;
choose a new directory for the next build. This prevents old `.mcp.json` files
from being retained in a rebuilt package. A failed build removes its temporary
files and leaves the destination available for a retry. The app ID is a reference, not a
credential. Never put access tokens, API keys, or OAuth client secrets in it.

The build produces:

```text
dist/chatgpt/
  .agents/plugins/marketplace.json
  plugins/flowlines-chatgpt/
    .codex-plugin/plugin.json
    .app.json
    assets/logo.png
    skills/
    LICENSE
  flowlines-chatgpt.zip
```

The manifest points `apps` to `./.app.json`. That file contains the registered
app ID with `required: true`. There are no MCP server declarations or hooks.
The ZIP contains the plugin files at its root, including the dotfiles.

For a local trial, add the generated directory as a local marketplace:

```sh
codex plugin marketplace add ./dist/chatgpt
```

Refresh the ChatGPT desktop app, select **Flowlines for ChatGPT** in the
Plugins Directory's marketplace picker, and install the plugin. The ZIP is a
portable copy of the same package; it does not create a connection or publish
the plugin by itself.

The committed `chatgpt/` marketplace is generated from the desktop source.
After changes to the source skills, plugin version, or connection ID, build
into a new directory:

```sh
python3 scripts/build_chatgpt_plugin.py \
  --app-id "$FLOWLINES_CHATGPT_APP_ID" \
  --output dist/chatgpt-next
```

Review the output and replace `chatgpt/.agents/` and `chatgpt/plugins/` with
the generated copies through a PR. The packaging tests compare these committed
files with a fresh build so that copied skills and metadata cannot drift.
Do not import the root desktop marketplace for ChatGPT web. `dist/` is reserved
for local runs and is ignored; generated ZIPs under `chatgpt/` are also ignored.

Building a ZIP or importing skills alone does not prove that the connection
works. Do not mark [FLO-177](https://linear.app/flowline/issue/FLO-177/make-flowlines-plugin-work-in-chatgpt)
complete until the live checks below pass.

## Verify before release

1. Install or sync the generated package and start a fresh ChatGPT web chat.
2. Type `@Flowlines` and select **Flowlines for ChatGPT**: ask it to list the
   workspaces you can access. Confirm an
   actual `get_workspace` call returns your workspace data.
3. Select a namespace from that response and ask for its overview. Confirm an
   actual `get_context` call uses the selected namespace and returns data.
4. Disconnect or use a user without access and confirm ChatGPT requests sign-in
   or reports unavailable access without inventing workspace data.
5. Record the registered app ID, package version, test time, and results. Avoid
   storing workspace payloads or credentials in this public repository.
6. Run `scripts/validate_plugins.sh` and verify the existing desktop clients
   still discover the `flowlines` MCP server and can query a workspace.

Offline packaging checks run with:

```sh
python3 -m unittest discover -s scripts -p 'test_chatgpt_plugin.py'
```

These run without contacting ChatGPT or Flowlines. They verify the package
and archive with a fixture ID, app ID handling,
skill resources, exclusion of local cache files, cleanup after a failed build,
preservation of the desktop source, and consistency of the committed workspace
package with a fresh build. The CI manifests job also runs
`scripts/validate_plugins.sh`, which uses the pinned CLI to install the generated
fixture package in a temporary home and check that it registers no desktop
MCP server before installing the original desktop package. These checks do
not verify that a real app exists or that ChatGPT can authenticate.

The copied `agents/openai.yaml` files retain the desktop `$skill` prompt syntax
required by the shared skill validator. In ChatGPT, select skills with `@`;
the generated plugin's starter prompts use plain language.

## OAuth discovery check

On 2026-09-08, production returned an unauthenticated `401` with
`x-amzn-remapped-www-authenticate` instead of the standard `WWW-Authenticate`
header. The public protected-resource metadata endpoint returned `200`.
This is a separate compatibility risk, not proof that it caused the missing
tools. Check the public endpoint and preserve the standard challenge header
through the gateway before the end-to-end authentication test.
[FLO-178](https://linear.app/flowline/issue/FLO-178/preserve-the-mcp-oauth-challenge-header-through-the-public-gateway)
tracks the infrastructure fix and blocks the FLO-177 live check. It proposes
a scoped Cloudflare response-header transform and requires an external HTTP
smoke check through the gateway.

## Public directory submission

A workspace app reference does not publish Flowlines to the public directory.
Use **With MCP** in the OpenAI submission portal and submit
`https://api.flowlines.ai/mcp` directly, with authentication, review materials,
and the analysis skills. **Skills only** is for packages that contain skills
alone. The portal does not publish a reference to an existing integration.
Public publication requires a separate review.

## References

- [Workspace import, desktop-only packages, and app references](https://learn.chatgpt.com/docs/enterprise/plugin-management)
- [Register and package an MCP connection](https://developers.openai.com/plugins/build/plugins)
- [OAuth requirements](https://developers.openai.com/plugins/build/auth)
- [Public submission requirements](https://developers.openai.com/plugins/deploy/submission)
- [API Gateway header remapping](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-known-issues.html)
