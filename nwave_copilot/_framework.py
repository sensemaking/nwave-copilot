"""Framework source location utilities for nwave-copilot.

Resolves paths to nWave source assets (agents, skills, tasks) whether running
from an installed package (bundled data) or directly from the source tree.
"""

from pathlib import Path


def get_package_root() -> Path:
    """Return the root of the installed nwave_copilot package."""
    return Path(__file__).parent


def get_framework_source() -> Path:
    """Return the directory containing bundled nWave framework assets.

    When installed via pip, assets are bundled alongside the Python code.
    When running from the source tree, assets live two levels up.
    """
    # Installed layout: nwave_copilot/ sits next to bundled nWave/
    bundled = get_package_root().parent / "nWave"
    if bundled.exists():
        return bundled.parent  # parent of nWave/ — contains agents/, skills/, tasks/

    # Source-tree fallback: packages/nwave-copilot/ → repo root
    repo_root = get_package_root().parent.parent.parent
    nwave_dir = repo_root / "nWave"
    if nwave_dir.exists():
        return repo_root

    raise FileNotFoundError(
        "Cannot locate nWave framework assets. "
        "Ensure nwave-copilot is installed correctly or run from the repository root."
    )


def get_agents_source() -> Path:
    """Return the path to the nWave/agents/ directory."""
    return get_framework_source() / "nWave" / "agents"


def get_skills_source() -> Path:
    """Return the path to the nWave/skills/ directory."""
    return get_framework_source() / "nWave" / "skills"


def get_tasks_source() -> Path:
    """Return the path to the nWave/tasks/nw/ directory."""
    return get_framework_source() / "nWave" / "tasks" / "nw"


def get_copilot_agents_dir() -> Path:
    """Return the personal Copilot agents directory (~/.copilot/agents/).

    Copilot uses ~/.copilot/ on all platforms (consistent with ~/.copilot/skills/).
    """
    return Path.home() / ".copilot" / "agents"


def get_copilot_skills_dir() -> Path:
    """Return the personal Copilot skills directory (~/.copilot/skills/)."""
    return Path.home() / ".copilot" / "skills"
