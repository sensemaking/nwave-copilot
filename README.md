# nwave-copilot

GitHub Copilot CLI plugin for the [nWave](https://github.com/nwave-ai/nwave) software development framework.

nWave is a six-wave AI-assisted development methodology (DISCOVER → DISCUSS → DESIGN → DEVOP → DISTILL → DELIVER) with 22 specialised agents, rich skills, and optional DES (Deterministic Execution System) hooks that enforce TDD discipline in the DELIVER wave.

## Installation

### Method 1: Copilot Marketplace (Recommended)

1.  **Install the Python package** (required for hooks execution):
    ```bash
    # Install directly from the repository
    pip install git+https://github.com/nwave-ai/nwave.git
    ```

2.  **Add the plugin from the marketplace**:
    ```bash
    copilot plugin marketplace add nwave-ai/nwave
    ```

    This installs the latest agents, skills, and hook configurations directly from GitHub.

### Method 2: Manual Installation (Legacy)

```bash
pip install git+https://github.com/nwave-ai/nwave.git
```

## Usage

### Step 1 – Personal install (run once)

Installs agents and skills to your personal Copilot config directory.
Agents and skills are then available in **all** your projects.

```bash
nwave-copilot install
```

- Agents → `~/.config/copilot/agents/nw-*.agent.md`
- Skills → `~/.copilot/skills/nw-*/SKILL.md`

To remove:

```bash
nwave-copilot uninstall
```

### Step 2 – Project init (run per project)

Adds DES enforcement hooks and prompt files to the current project.
Run from inside a git repository.

```bash
cd your-project
nwave-copilot init
```

- Hook configs → `.github/hooks/nw-*.json`
- Prompt files → `.github/prompts/nw-*.prompt.md`

Commit these files so your whole team gets DES enforcement.

To remove:

```bash
nwave-copilot deinit
```

## Feature Comparison: Claude Code vs Copilot CLI

| Feature | Claude Code | Copilot CLI |
|---|---|---|
| 22 nWave agents | ✅ | ✅ |
| Skills (68 files) | ✅ | ✅ |
| `/nw:*` slash commands | ✅ global | ✅ as prompt files (project-scoped) |
| DES PreToolUse hook | ✅ | ✅ |
| DES PostToolUse hook | ✅ | ✅ |
| DES SubagentStop hook | ✅ (transcript) | ✅ (signal files) |
| Per-agent `maxTurns` | ✅ | ❌ not supported |
| Per-agent model selection | ✅ | ❌ not supported |
| Personal hooks install | ✅ | ❌ hooks are always project-scoped |

## DES (Deterministic Execution System)

DES enforces TDD discipline during the DELIVER wave. It requires `nwave-copilot init`
in each project because Copilot hooks are always project-scoped (`.github/hooks/`).

The DES Python logic is part of the globally-installed `nwave-copilot` package and
is invoked by the project-level hook configs via `python -m des.adapters.drivers.hooks.copilot_hook_adapter`.
