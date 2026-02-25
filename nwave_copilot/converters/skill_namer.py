"""Skill naming strategy for GitHub Copilot skill directories.

In Claude Code, skills live in agent-scoped subdirectories:
  nWave/skills/software-crafter/tdd-methodology.md

In Copilot, skills use a flat global namespace:
  ~/.copilot/skills/<name>/SKILL.md

Naming rules:
  - All skills get an "nw-" prefix to avoid polluting the global namespace.
  - Skills whose filename conflicts across multiple agent directories get
    an agent-folder qualifier: nw-{agent-folder}-{skill-name}
  - Unique skills get the simpler form: nw-{skill-name}
"""

from pathlib import Path


# Skill filenames that appear in multiple agent directories with different content.
# These require agent-folder qualification to avoid collision.
CONFLICTING_SKILL_NAMES: frozenset[str] = frozenset(
    {
        "critique-dimensions",
        "review-criteria",
        "review-dimensions",
    }
)


def get_skill_dir_name(agent_folder: str, skill_path: Path) -> str:
    """Return the Copilot skill directory name for a given skill file.

    Args:
        agent_folder: The agent subdirectory the skill lives in
                      (e.g. "software-crafter").
        skill_path: Path to the skill .md file.

    Returns:
        Directory name to use under ~/.copilot/skills/
        e.g. "nw-tdd-methodology" or "nw-software-crafter-review-dimensions"
    """
    stem = skill_path.stem  # filename without extension
    if stem in CONFLICTING_SKILL_NAMES:
        return f"nw-{agent_folder}-{stem}"
    return f"nw-{stem}"
