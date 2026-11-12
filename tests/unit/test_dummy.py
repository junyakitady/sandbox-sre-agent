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

"""Unit tests for the SRE Agent and GEAP Sandbox tool."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from google.adk.models import Gemini
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from app.agent import _SKILLS_DIR, root_agent, sre_skill_toolset
from app.tools import run_in_sandbox


def test_agent_configuration() -> None:
    """Verifies that root_agent uses gemini-4-argon with retry_options and registers tools and skills."""
    assert root_agent.name == "sre_agent"
    assert isinstance(root_agent.model, Gemini)
    assert root_agent.model.model == "gemini-4-argon"
    assert root_agent.model.retry_options is not None
    assert len(root_agent.tools) == 3
    assert isinstance(sre_skill_toolset, SkillToolset)


def test_sre_skills_frontmatter_and_scriptless_structure() -> None:
    """Verifies all SRE skills pass ADK validation, stay under 500 lines, and contain no custom scripts."""
    expected_skills = {
        "blameless-postmortem",
        "cloud-logging-investigation",
        "gcp-mitigation-playbooks",
    }
    skill_dirs = [
        d for d in sorted(_SKILLS_DIR.iterdir()) if d.is_dir() and (d / "SKILL.md").exists()
    ]
    assert {d.name for d in skill_dirs} == expected_skills

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        lines = skill_md.read_text(encoding="utf-8").splitlines()
        assert len(lines) < 500, f"{skill_md} exceeds 500 lines"

        skill = load_skill_from_dir(skill_dir)
        assert skill.name == skill_dir.name
        assert 0 < len(skill.description) <= 1024
        assert skill.resources.list_scripts() == []

    exposed_tool_names = [t.name for t in sre_skill_toolset._tools if sre_skill_toolset._is_tool_selected(t, None)]
    assert exposed_tool_names == ["load_skill", "load_skill_resource"]


@patch("app.tools._get_access_token", return_value="fake-oauth-token")
@patch("app.tools._get_or_create_sandbox_template")
@patch("app.tools._get_sandbox_client")
def test_run_in_sandbox_creates_and_reuses_session_sandbox(
    mock_get_client: MagicMock,
    mock_get_template: MagicMock,
    _mock_get_token: MagicMock,
) -> None:
    """Verifies session-scoped sandbox creation, reuse, and execute_bash invocation."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_get_template.return_value = (
        "projects/llm20260121/locations/us-central1/reasoningEngines/123",
        "projects/llm20260121/locations/us-central1/reasoningEngines/123/sandboxEnvironmentTemplates/456",
    )

    sandbox_name = (
        "projects/llm20260121/locations/us-central1/reasoningEngines/123"
        "/sandboxEnvironments/789"
    )
    mock_client.sandboxes.create.return_value = SimpleNamespace(
        response=SimpleNamespace(name=sandbox_name)
    )
    mock_client.sandboxes.get.return_value = SimpleNamespace(state="STATE_RUNNING")
    mock_client.sandboxes.execute_bash.return_value = {
        "stdout": '[{"severity": "ERROR"}]',
        "stderr": "",
        "returncode": 0,
        "duration_ms": 120,
    }

    fake_context = SimpleNamespace(state={})

    # First call creates the sandbox and stores it in session state
    res1 = run_in_sandbox(
        "gcloud logging read 'severity>=ERROR' --limit=5", fake_context
    )
    assert res1["sandbox_name"] == sandbox_name
    assert res1["returncode"] == 0
    assert res1["stdout"] == '[{"severity": "ERROR"}]'
    assert fake_context.state["sandbox_name"] == sandbox_name
    assert mock_client.sandboxes.create.call_count == 1

    # Second call reuses the running sandbox from session state and redacts tokens
    mock_client.sandboxes.execute_bash.return_value = {
        "stdout": "TOKEN=fake-oauth-token",
        "stderr": "err: fake-oauth-token",
        "returncode": 0,
        "duration_ms": 10,
    }
    res2 = run_in_sandbox("env", fake_context)
    assert res2["sandbox_name"] == sandbox_name
    assert res2["stdout"] == "TOKEN=[REDACTED]"
    assert res2["stderr"] == "err: [REDACTED]"
    assert mock_client.sandboxes.create.call_count == 1
    assert mock_client.sandboxes.get.call_count == 1
