# Flowlines in ChatGPT

The desktop package at `plugins/flowlines` declares its server in `.mcp.json`.
ChatGPT workspace import marks a plugin with MCP server declarations as
**Desktop only**, including remote HTTPS servers. A ChatGPT web package must
reference a registered app through `.app.json` instead.

The build command below creates a separate package with the same Flowlines
name and logo. It includes weekly reviews, release checks, session
investigations, and cohort analysis. Instrumentation, local telemetry setup,
and local diagnostics remain in the desktop package. The source skills and
existing marketplace are not modified.

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
from being retained in a rebuilt package. The app ID is a reference, not a
credential. Never put access tokens, API keys, or OAuth client secrets in it.

The build produces:

```text
dist/chatgpt/
  .agents/plugins/marketplace.json
  plugins/flowlines/
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

Install the package through a local marketplace or the workspace's supported
plugin upload flow, then publish it to the intended workspace roles as an
admin. For GitHub workspace import, commit the generated marketplace and
`plugins/` tree to a separate marketplace directory or repository that the
workspace can read. Import that directory as the marketplace **Path**; do not
import this repository's root desktop marketplace for ChatGPT web. `dist/` is
ignored so a test connection is not published by accident.

Building a ZIP or importing skills alone does not prove that the connection
works. Do not mark [FLO-177](https://linear.app/flowline/issue/FLO-177/make-flowlines-plugin-work-in-chatgpt)
complete until the live checks below pass.

## Verify before release

1. Install or sync the generated package and start a fresh ChatGPT web chat.
2. Invoke `@Flowlines`: ask it to list the workspaces you can access. Confirm an
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

These use a fixture ID. They verify the package and archive, app ID handling,
skill resources, and preservation of the desktop source. They do not verify
that a real app exists or that ChatGPT can authenticate.

## OAuth discovery check

On 2026-09-08, production returned an unauthenticated `401` with
`x-amzn-remapped-www-authenticate` instead of the standard `WWW-Authenticate`
header. The public protected-resource metadata endpoint returned `200`.
This is a separate compatibility risk, not proof that it caused the missing
tools. Check the public endpoint and preserve the standard challenge header
through the gateway before the end-to-end authentication test. The gateway
configuration is outside this plugin repository.

## Public directory submission

A workspace app reference does not publish Flowlines to the public directory.
Use **With MCP** in the OpenAI submission portal and submit
`https://api.flowlines.ai/mcp` directly, with authentication, review materials,
and the analysis skills. Do not use **Skills only** to publish the connection:
that path removes `.app.json`. The portal does not publish a reference to an
existing integration. Public publication requires a separate review.

## References

- [Workspace import, desktop-only packages, and app references](https://learn.chatgpt.com/docs/enterprise/plugin-management)
- [Register and package an MCP connection](https://developers.openai.com/plugins/build/plugins)
- [OAuth requirements](https://developers.openai.com/plugins/build/auth)
- [Public submission requirements](https://developers.openai.com/plugins/deploy/submission)
- [API Gateway header remapping](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-known-issues.html)
