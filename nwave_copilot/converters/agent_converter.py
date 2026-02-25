"""Agent frontmatter converter: Claude Code → GitHub Copilot CLI format.

Transforms .md agent files with Claude Code frontmatter into .agent.md files
with Copilot-compatible frontmatter.

Claude Code frontmatter fields:
  name, description, model, tools (comma-separated or YAML list), maxTurns, skills

Copilot frontmatter fields:
  name, description, tools (YAML list using Copilot tool aliases)

Dropped: model, maxTurns, skills (Copilot auto-selects skills by description)
"""

import re
from pathlib import Path
from typing import NamedTuple

import yaml


# Claude Code tool name → Copilot tool alias
TOOL_MAP: dict[str, str] = {
    "Read": "read",
    "Write": "edit",
    "Edit": "edit",
    "Bash": "execute",
    "Glob": "search",
    "Grep": "search",
    "Task": "agent",
    "WebFetch": "fetch",
    "WebSearch": "search",
    "AskUserQuestion": None,  # type: ignore[assignment]  # dropped — no equivalent
}

# Fields that exist in Claude Code frontmatter but are not supported in Copilot
DROPPED_FIELDS = {"model", "maxTurns", "skills"}


class ConvertedAgent(NamedTuple):
    """Result of converting a single agent file."""

    source_path: Path
    target_filename: str  # e.g. "nw-software-crafter.agent.md"
    content: str  # Full file content ready to write


def _parse_tools(tools_value: object) -> list[str]:
    """Parse tools from Claude Code frontmatter (string or list)."""
    if isinstance(tools_value, list):
        return [str(t).strip() for t in tools_value]
    if isinstance(tools_value, str):
        # Handle bracket notation: [Read, Glob, Grep]
        cleaned = tools_value.strip().strip("[]")
        return [t.strip() for t in cleaned.split(",") if t.strip()]
    return []


def _map_tools(claude_tools: list[str]) -> list[str]:
    """Convert Claude Code tool names to Copilot aliases, deduplicating."""
    seen: set[str] = set()
    result: list[str] = []
    for tool in claude_tools:
        alias = TOOL_MAP.get(tool)
        if alias is not None and alias not in seen:
            seen.add(alias)
            result.append(alias)
    return result


def _strip_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from a markdown file.

    Returns (frontmatter_dict, body_text).
    """
    pattern = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
    match = pattern.match(content)
    if not match:
        return {}, content
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = content[match.end():]
    return fm, body


def _update_agent_body(body: str, agent_name: str) -> str:
    """Apply body text updates for Copilot compatibility.

    - Remove AskUserQuestion tool references
    - Update Co-Authored-By trailers from Anthropic to GitHub Copilot
    """
    # Remove AskUserQuestion tool references
    body = re.sub(r"\bAskUserQuestion\b", "conversational questioning", body)

    # Update Co-Authored-By trailers
    body = body.replace(
        "Co-Authored-By: Claude (Anthropic)",
        "Co-Authored-By: Copilot (GitHub)",
    )
    body = body.replace(
        "Co-authored-by: Claude (Anthropic)",
        "Co-authored-by: Copilot (GitHub)",
    )

    return body


def convert_agent(source_path: Path) -> ConvertedAgent:
    """Convert a Claude Code agent .md file to Copilot .agent.md format.

    Args:
        source_path: Path to the source .md agent file.

    Returns:
        ConvertedAgent with the target filename and converted content.
    """
    content = source_path.read_text(encoding="utf-8")
    fm, body = _strip_frontmatter(content)

    name = fm.get("name", source_path.stem)
    description = fm.get("description", "")

    # Convert tools
    raw_tools = _parse_tools(fm.get("tools", []))
    copilot_tools = _map_tools(raw_tools)

    # Build new frontmatter (only Copilot-supported fields)
    new_fm_lines = ["---"]
    new_fm_lines.append(f"name: {name}")
    if description:
        # Wrap description in quotes if it contains special chars
        desc_yaml = yaml.dump({"d": description}, default_flow_style=False)
        desc_value = desc_yaml.split("d: ", 1)[1].rstrip("\n")
        new_fm_lines.append(f"description: {desc_value}")
    if copilot_tools:
        new_fm_lines.append("tools:")
        for tool in copilot_tools:
            new_fm_lines.append(f"  - {tool}")
    new_fm_lines.append("---")
    new_fm_lines.append("")

    # Update body text
    updated_body = _update_agent_body(body, name)

    new_content = "\n".join(new_fm_lines) + updated_body

    # Target filename: .md → .agent.md
    target_filename = source_path.stem + ".agent.md"

    return ConvertedAgent(
        source_path=source_path,
        target_filename=target_filename,
        content=new_content,
    )
