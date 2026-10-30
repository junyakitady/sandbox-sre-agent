# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tools for the SRE Agent: GEAP Shell Sandbox and Google Developer Knowledge MCP.

Why ADK's built-in `AgentEngineSandboxCodeExecutor` is not used as-is:
1. No Sandbox Template / Egress Control support:
   `AgentEngineSandboxCodeExecutor` hardcodes `spec={'code_execution_environment': {}}`
   when calling `sandboxes.create()`, with no parameter for `sandbox_environment_template`.
   Without a template setting `egress_control_config={"internet_access": True}`,
   outbound calls to `logging.googleapis.com` are blocked by default.
2. Python Kernel (`execute_code`) vs Shell Environment (`execute_bash`):
   It invokes `sandboxes.execute_code()` against `code_execution_environment`
   rather than `sandboxes.execute_bash()` against `DEFAULT_CONTAINER_CATEGORY_SHELL_SANDBOX`.
3. No Service Account OAuth Token Injection Hook:
   GEAP Sandboxes do not expose a metadata server (`169.254.169.254`) inside the
   container, so the host Agent Runtime must refresh its Service Account ADC token
   and inject `CLOUDSDK_AUTH_ACCESS_TOKEN` per execution.
4. Tool Calling Mode Conflict:
   `BaseCodeExecutor` intercepts Markdown ```tool_code blocks via an LLM request
   processor instead of standard Function Calling, which conflicts with `McpToolset`.
"""

import os
import shlex
import time
from typing import Any

import agentplatform
import google.auth
import google.auth.transport.requests
from google.adk.tools import ToolContext
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "llm20260121")
SANDBOX_LOCATION = os.environ.get("SANDBOX_LOCATION", "us-central1")
SANDBOX_ENGINE_DISPLAY_NAME = "sre-agent-sandbox-host"
SANDBOX_TEMPLATE_DISPLAY_NAME = "sre-shell-egress-template"

_sandbox_client: agentplatform.Client | None = None
_cached_template_name: str | None = None
_cached_engine_name: str | None = None

# Lightweight `gcloud logging read` shim for DEFAULT_CONTAINER_CATEGORY_SHELL_SANDBOX
# (which provides Python 3.11 in /opt/venv/bin/python3 without the 500MB Cloud SDK).
_GCLOUD_SHIM_SCRIPT = """#!/opt/venv/bin/python3
import argparse, datetime, json, os, re, sys, urllib.error, urllib.request

def main():
    args = sys.argv[1:]
    if len(args) < 2 or args[0] != "logging" or args[1] != "read":
        sys.stderr.write("Supported in sandbox: gcloud logging read [FILTER] [--project=P] [--limit=N] [--freshness=DURATION] [--order=desc|asc] [--format=json]\\n")
        sys.exit(2)
    p = argparse.ArgumentParser(prog="gcloud logging read")
    p.add_argument("log_filter", nargs="?", default="")
    p.add_argument("--project", default=os.environ.get("CLOUDSDK_CORE_PROJECT", ""))
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--freshness", default="")
    p.add_argument("--order", default="desc")
    p.add_argument("--format", default="json")
    ns, _ = p.parse_known_args(args[2:])
    flt = ns.log_filter.strip()
    if ns.freshness:
        m = re.fullmatch(r"(\\d+)([smhd])", ns.freshness.strip())
        if m:
            val, unit = int(m.group(1)), m.group(2)
            delta = {"s": datetime.timedelta(seconds=val), "m": datetime.timedelta(minutes=val), "h": datetime.timedelta(hours=val), "d": datetime.timedelta(days=val)}[unit]
            ts = (datetime.datetime.now(datetime.timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
            flt = f'({flt}) AND timestamp>="{ts}"' if flt else f'timestamp>="{ts}"'
    body = {
        "resourceNames": [f"projects/{ns.project}"],
        "pageSize": min(ns.limit, 1000),
        "orderBy": f"timestamp {ns.order}",
    }
    if flt:
        body["filter"] = flt
    token = os.environ["CLOUDSDK_AUTH_ACCESS_TOKEN"]
    req = urllib.request.Request(
        "https://logging.googleapis.com/v2/entries:list",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            entries = json.loads(resp.read().decode()).get("entries", [])[:ns.limit]
            print(json.dumps(entries, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        sys.stderr.write(e.read().decode() + "\\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
"""


def _get_sandbox_client() -> agentplatform.Client:
    global _sandbox_client
    if _sandbox_client is None:
        _sandbox_client = agentplatform.Client(
            project=PROJECT_ID,
            location=SANDBOX_LOCATION,
        )
    return _sandbox_client


def _get_or_create_sandbox_template(
    client: agentplatform.Client,
) -> tuple[str, str]:
    """Resolves or creates the parent engine and Egress-enabled Shell Sandbox template."""
    global _cached_engine_name, _cached_template_name
    if _cached_engine_name and _cached_template_name:
        return _cached_engine_name, _cached_template_name

    engine_name = os.environ.get("AGENT_ENGINE_RESOURCE_NAME")
    if not engine_name:
        for runtime in client.runtimes.list():
            if runtime.api_resource.display_name in (
                "sre-agent",
                SANDBOX_ENGINE_DISPLAY_NAME,
            ):
                engine_name = runtime.api_resource.name
                break
    if not engine_name:
        created_runtime = client.runtimes.create(
            config={"display_name": SANDBOX_ENGINE_DISPLAY_NAME}
        )
        engine_name = created_runtime.api_resource.name

    template_name = None
    for tmpl in client.sandboxes.templates.list(name=engine_name):
        if tmpl.display_name == SANDBOX_TEMPLATE_DISPLAY_NAME:
            template_name = tmpl.name
            break
    if not template_name:
        op = client.sandboxes.templates.create(
            name=engine_name,
            display_name=SANDBOX_TEMPLATE_DISPLAY_NAME,
            config={
                "default_container_environment": {
                    "default_container_category": "DEFAULT_CONTAINER_CATEGORY_SHELL_SANDBOX",
                },
                "egress_control_config": {
                    "internet_access": True,
                },
            },
        )
        template_name = op.response.name

    _cached_engine_name = engine_name
    _cached_template_name = template_name
    return engine_name, template_name


def _get_access_token() -> str:
    """Refreshes and returns a short-lived OAuth2 access token from ADC."""
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def run_in_sandbox(command: str, tool_context: ToolContext) -> dict[str, Any]:
    """Executes a bash command (`gcloud` or `python3`) in an isolated GEAP Shell Sandbox.

    A dedicated sandbox instance is created per ADK session and reused across turns,
    so temporary files in `/tmp` persist within the conversation.

    Args:
        command: The bash command to execute (e.g. `gcloud logging read ...` or `python3 -c ...`).
    """
    client = _get_sandbox_client()
    engine_name, template_name = _get_or_create_sandbox_template(client)

    sandbox_name = tool_context.state.get("sandbox_name")
    if sandbox_name:
        try:
            sbx = client.sandboxes.get(name=sandbox_name)
            if str(sbx.state) != "SandboxState.STATE_RUNNING" and sbx.state != "STATE_RUNNING":
                sandbox_name = None
        except Exception:
            sandbox_name = None

    if not sandbox_name:
        op = client.sandboxes.create(
            name=engine_name,
            config={
                "display_name": "sre-session-sandbox",
                "sandbox_environment_template": template_name,
                "ttl": "3600s",
                "wait_for_completion": True,
            },
        )
        sandbox_name = op.response.name
        tool_context.state["sandbox_name"] = sandbox_name

    token = _get_access_token()
    full_cmd = (
        "if [ ! -x /tmp/bin/gcloud ]; then "
        "mkdir -p /tmp/bin && cat <<'GCLOUD_EOF' > /tmp/bin/gcloud && chmod +x /tmp/bin/gcloud\n"
        f"{_GCLOUD_SHIM_SCRIPT}"
        "GCLOUD_EOF\n"
        "fi\n"
        'export PATH="/tmp/bin:$PATH"\n'
        f"export CLOUDSDK_AUTH_ACCESS_TOKEN={shlex.quote(token)}\n"
        f"export CLOUDSDK_CORE_PROJECT={shlex.quote(PROJECT_ID)}\n"
        f"{command}"
    )

    result: dict[str, Any] = {}
    for attempt in range(6):
        try:
            result = client.sandboxes.execute_bash(
                name=sandbox_name,
                command=full_cmd,
            )
            break
        except Exception as exc:
            if "Unable to reach the sandbox environment" in str(exc) and attempt < 5:
                time.sleep(2 * (attempt + 1))
                continue
            raise

    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    if token:
        stdout = stdout.replace(token, "[REDACTED]")
        stderr = stderr.replace(token, "[REDACTED]")

    return {
        "sandbox_name": sandbox_name,
        "returncode": result.get("returncode", 0),
        "stdout": stdout,
        "stderr": stderr,
    }


def _mcp_headers(_readonly_context: Any = None) -> dict[str, str]:
    """Provides ADC Bearer token and billing project header for Developer Knowledge MCP."""
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "X-Goog-User-Project": PROJECT_ID,
    }


developer_knowledge_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://developerknowledge.googleapis.com/mcp",
    ),
    header_provider=_mcp_headers,
)
