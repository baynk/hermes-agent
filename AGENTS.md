# Hermes Agent - Development Guide

## Purpose

This file is the operating guide for AI coding agents and developers working on `hermes-agent`.

Hermes is a large, multi-surface agent system: CLI, TUI, gateway, tools, plugins, skills, memory, cron, kanban, model providers, and profile-aware user state. The goal of this file is not to document every implementation detail. It is to keep agents oriented, prevent common regressions, and point edits toward the correct subsystem.

Use the filesystem as the source of truth. File counts, exact module sizes, and provider catalogs change often.

---

## Working Principles

1. **Make the smallest safe change.**
   Prefer narrow patches over broad rewrites. Preserve existing behavior unless the task explicitly requires changing it.

2. **Understand the active subsystem before editing.**
   Hermes has several parallel mechanisms that look similar but are intentionally separate: general plugins, memory plugins, model-provider plugins, skills, toolsets, gateway adapters, and TUI gateway calls.

3. **Preserve prompt caching.**
   Do not mutate loaded system-prompt state mid-conversation unless the code path is explicitly cache-aware. Changes to tools, skills, memory, or system prompt content should normally take effect in the next session unless a command has a deliberate `--now` style invalidation path.

4. **Keep profiles isolated.**
   Anything that reads or writes Hermes state must use profile-aware paths. Never hardcode `~/.hermes` in code that touches runtime state.

5. **Use the test wrapper.**
   Always run tests through `scripts/run_tests.sh`, not raw `pytest`, unless there is a specific reason the wrapper cannot be used.

6. **Do not wire in dead code without an end-to-end check.**
   If a module is unused, assume there may be a reason. Validate the real import and resolution path against a temporary `HERMES_HOME` before connecting it to production flow.

---

## Development Environment

Prefer `.venv`, falling back to `venv` when needed.

```bash
if [ -d .venv ]; then
  source .venv/bin/activate
elif [ -d venv ]; then
  source venv/bin/activate
fi
```

`scripts/run_tests.sh` probes `.venv`, then `venv`, then `$HOME/.hermes/hermes-agent/venv` for worktrees that share a virtual environment with the main checkout.

User state lives under the active Hermes home:

- Config: `config.yaml`
- Secrets: `.env`
- Logs: `logs/agent.log`, `logs/errors.log`, and `logs/gateway.log` when the gateway is running

Use `hermes logs [--follow] [--level ...] [--session ...]` for log inspection.

---

## Repository Landmarks

The tree below is intentionally non-exhaustive. Use it as a navigation map, not a snapshot.

```text
hermes-agent/
├── run_agent.py              # AIAgent and the core conversation loop
├── model_tools.py            # Tool discovery, schema assembly, function-call dispatch
├── toolsets.py               # Toolset definitions and core tool bundles
├── cli.py                    # Classic interactive CLI orchestration
├── hermes_state.py           # SQLite session store and search
├── hermes_constants.py       # Profile-aware path helpers
├── hermes_logging.py         # Profile-aware logging setup
├── batch_runner.py           # Parallel batch processing
├── agent/                    # Provider adapters, memory, compression, caching, internals
├── hermes_cli/               # CLI commands, setup, plugins, skins, dashboard server
├── tools/                    # Built-in tools and tool registry
│   └── environments/         # Local, Docker, SSH, Modal, Daytona, Singularity backends
├── gateway/                  # Messaging gateway runtime and platform adapters
│   ├── platforms/            # Telegram, Discord, Slack, WhatsApp, Signal, Matrix, etc.
│   └── builtin_hooks/        # Always-registered gateway hooks
├── plugins/                  # General, memory, model-provider, context, image, kanban plugins
├── skills/                   # Built-in skills loaded by default
├── optional-skills/          # Heavy or niche skills installed explicitly
├── ui-tui/                   # Ink/React terminal UI
├── tui_gateway/              # Python JSON-RPC backend for the TUI
├── acp_adapter/              # ACP integration for editors
├── cron/                     # Scheduled jobs
├── scripts/                  # Test wrapper, release scripts, maintenance scripts
├── website/                  # Documentation site
└── tests/                    # Pytest suite
```

### Core dependency chain

```text
tools/registry.py
    ↓
tools/*.py
    ↓
model_tools.py
    ↓
run_agent.py, cli.py, batch_runner.py, gateway, environments
```

Tool files register themselves at import time. Tool discovery imports the files. A tool still must be included in an enabled toolset before an agent can use it. Do not add manual import lists unless the current code path explicitly requires it.

---

## Core Agent Runtime

`AIAgent` lives in `run_agent.py`. Its full initializer has many parameters for credentials, routing, callbacks, session context, budget, checkpoints, reasoning config, credential pools, platform metadata, and more.

The two most important public entry points are:

```python
agent.chat(message: str) -> str
agent.run_conversation(
    user_message: str,
    system_message: str | None = None,
    conversation_history: list | None = None,
    task_id: str | None = None,
) -> dict
```

The conversation loop is synchronous. It repeatedly calls the model, handles tool calls, appends tool results, tracks iteration budget, checks interrupts, and returns when the model produces a final response.

Messages follow the OpenAI-style roles:

```text
system, user, assistant, tool
```

Reasoning content is stored separately on assistant messages, commonly under a `reasoning` field.

---

## Tool System

### Built-in tools

For most custom or local-only tools, use a plugin. Do not edit Hermes core unless the tool is intended to ship as part of the base system.

A built-in core tool requires two steps:

1. Add a `tools/<name>.py` module that calls `registry.register(...)` at import time.
2. Add the tool name to an appropriate toolset in `toolsets.py`.

Tool handlers must return a JSON string.

Agent-level tools such as todo and memory are intercepted by `run_agent.py` before normal `handle_function_call()` dispatch. Check that path before changing tool routing.

Minimal shape:

```python
import json
import os
from tools.registry import registry


def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))


def example_tool(param: str, task_id: str | None = None) -> str:
    return json.dumps({"success": True, "data": "..."})


registry.register(
    name="example_tool",
    toolset="example",
    schema={
        "name": "example_tool",
        "description": "...",
        "parameters": {...},
    },
    handler=lambda args, **kw: example_tool(
        param=args.get("param", ""),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

### Toolsets

All toolsets are defined in `toolsets.py` as a single `TOOLSETS` mapping. Platform adapters choose a base toolset, and most inherit from the core tool bundle.

Tool exposure is controlled through:

- `hermes tools`
- `tools.<platform>.enabled` in `config.yaml`
- `tools.<platform>.disabled` in `config.yaml`

Do not assume a tool from another toolset is available. Tool schema descriptions must not hardcode cross-tool recommendations. If a schema needs dynamic cross-tool guidance, add it during schema assembly in `model_tools.py` after availability is known.

### Path handling inside tools

Use profile-aware helpers:

```python
from hermes_constants import get_hermes_home, display_hermes_home
```

- Use `get_hermes_home()` for actual state paths.
- Use `display_hermes_home()` for user-facing messages and schema descriptions.

Never use `Path.home() / ".hermes"` for runtime state.

---

## Configuration and Secrets

Hermes uses two user-facing configuration surfaces:

```text
config.yaml   # Non-secret settings
.env          # Secrets only: API keys, tokens, passwords
```

### Adding config keys

Add non-secret settings to `DEFAULT_CONFIG` in `hermes_cli/config.py`.

Only bump `_config_version` when existing user config must be actively migrated or transformed. Adding a new key to an existing section is handled by deep merge and normally does not require a version bump.

Common top-level sections include:

```text
model, agent, terminal, compression, display, stt, tts,
memory, security, delegation, smart_model_routing, checkpoints,
auxiliary, curator, skills, gateway, logging, cron, profiles,
plugins, honcho
```

### Adding secrets

Add secret metadata to `OPTIONAL_ENV_VARS` in `hermes_cli/config.py`.

```python
"NEW_API_KEY": {
    "description": "What it is for",
    "prompt": "Display name",
    "url": "https://...",
    "password": True,
    "category": "tool",  # provider, tool, messaging, setting
}
```

Do not put timeouts, feature flags, paths, display preferences, or other non-secret settings in `.env`. If backward compatibility requires an environment variable, bridge from `config.yaml` into the environment in code.

### Config loaders

Know which loader your code path uses:

| Loader | Used by | Location |
|---|---|---|
| `load_cli_config()` | CLI mode | `cli.py` |
| `load_config()` | Tools, setup, most CLI subcommands | `hermes_cli/config.py` |
| Direct YAML load | Gateway runtime | `gateway/run.py`, `gateway/config.py` |

If a setting works in the CLI but not the gateway, or the reverse, check whether you updated the correct loader path.

### Working directory

- CLI mode uses the process current working directory.
- Messaging gateway mode uses `terminal.cwd` from `config.yaml`.

The old `MESSAGING_CWD` path is removed. `TERMINAL_CWD` in `.env` is also not canonical; use `terminal.cwd` in `config.yaml`.

---

## Profiles and Path Safety

Hermes supports isolated profiles. Each profile has its own `HERMES_HOME` for config, secrets, logs, memory, sessions, skills, gateway state, and other runtime files.

The profile override happens early in `hermes_cli/main.py` before most imports. Code that uses `get_hermes_home()` after import is profile-safe.

Rules:

1. Use `get_hermes_home()` for all runtime state.
2. Use `display_hermes_home()` for user-facing paths.
3. Do not hardcode `~/.hermes` in code or tests.
4. Tests that mock `Path.home()` should also set `HERMES_HOME`.
5. Gateway adapters with unique credentials should acquire and release scoped locks so two profiles do not use the same bot token or API key at once.
6. Profile operations are home-anchored, not active-profile-anchored. Profile listing must be able to see all profiles regardless of the currently selected one.

Test pattern:

```python
@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home
```

---

## CLI and Slash Commands

The classic CLI is orchestrated by `HermesCLI` in `cli.py`.

Important surfaces:

- Rich renders banners and panels.
- `prompt_toolkit` handles interactive input and autocomplete.
- The skin engine lives in `hermes_cli/skin_engine.py`.
- Slash commands are centrally defined in `hermes_cli/commands.py`.
- Skill slash commands are scanned from user skills and injected as user messages to preserve prompt caching.

### Slash command registry

All slash commands must be represented by a `CommandDef` in `COMMAND_REGISTRY`.

The registry feeds:

- CLI dispatch and help
- Gateway known-command handling
- Gateway help output
- Telegram bot command menus
- Slack subcommand routing
- Autocomplete

To add a slash command:

1. Add a `CommandDef` to `COMMAND_REGISTRY`.
2. Add CLI handling in `HermesCLI.process_command()`.
3. If gateway-supported, add gateway handling in `gateway/run.py`.
4. For persistent settings, use the config save helper rather than ad hoc writes.

Adding an alias should require only adding it to the existing command definition.

Commands that mutate loaded prompt state must be cache-aware. Prefer deferred effect for the next session, with explicit immediate invalidation only when the command is designed for it.

---

## TUI and Dashboard

The TUI is a real replacement for the classic CLI, not a thin wrapper.

```text
hermes --tui
  └─ Node / Ink frontend
       └─ stdio JSON-RPC
            └─ Python tui_gateway backend
                 └─ AIAgent, sessions, tools, slash logic
```

TypeScript owns rendering. Python owns sessions, tools, model calls, and slash-command execution.

Key surfaces:

| Surface | Ink side | Python side |
|---|---|---|
| Chat streaming | `app.tsx`, message components | `prompt.submit`, message events |
| Tool activity | thinking components | tool start/progress/complete events |
| Approvals | prompt components | approval request/respond methods |
| Session picker | session picker components | session list/resume methods |
| Slash commands | local handlers and fallthrough | `slash.exec`, command dispatch |
| Completions | completion hooks | slash/path completion methods |
| Theming | theme and branding data | gateway-ready skin payload |

### Dashboard rule

The dashboard embeds the real `hermes --tui` through a PTY bridge. Do not reimplement the primary chat transcript, composer, or slash-command flow in React.

If a dashboard change needs to affect the main chat experience, extend the Ink TUI. React dashboard panels may add supporting views such as sidebars, inspectors, summaries, status panels, and model pickers, but they must not become a second chat surface.

---

## Gateway

The gateway runs Hermes over messaging platforms such as Telegram, Discord, Slack, WhatsApp, Signal, Matrix, email, SMS, webhook, API server, and related adapters.

Platform adapters live under `gateway/platforms/`.

When adding or changing gateway behavior:

- Respect platform-specific base toolsets.
- Keep command handling aligned with the central slash-command registry.
- Use scoped locks for adapters with unique credentials.
- Do not let approval/control commands get trapped behind active-session guards.

Important pitfall: the gateway has two message guards when an agent is running.

1. The base adapter may queue messages while a session is active.
2. The gateway runner intercepts control commands such as stop, new, queue, status, approve, and deny.

Any new control command that must work while the agent is blocked must bypass both guards and be dispatched inline.

Background terminal processes can notify the gateway when complete. Notification verbosity is controlled by `display.background_process_notifications` in `config.yaml`.

---

## Plugins

Hermes has several plugin systems. Do not collapse them into one mechanism.

### General plugins

General plugins are discovered by the plugin manager from user plugins, local plugins, and entry points. A plugin exposes `register(ctx)` and may register:

- Lifecycle hooks
- Tools
- CLI subcommands

Hooks are invoked from the agent and tool orchestration paths.

Discovery is triggered as a side effect of importing `model_tools.py`. Code paths that read plugin state without importing `model_tools.py` first must call plugin discovery explicitly. Discovery should be idempotent.

### Memory-provider plugins

Memory providers implement the `MemoryProvider` interface and are orchestrated by the memory manager.

They have their own discovery path and optional setup hooks. CLI commands for memory plugins should only surface for the active provider.

Do not add new in-tree memory providers. New memory backends should ship as standalone plugin repos or entry-point plugins.

### Model-provider plugins

Model providers are a separate lazy discovery system. They register `ProviderProfile` objects and are scanned on first provider lookup or provider listing.

Scan order is generally:

1. Bundled model-provider plugins
2. User model-provider plugins
3. Legacy provider modules for backward compatibility

User plugins may override bundled providers of the same name.

The general plugin manager may record model-provider manifests but should not import them, because provider discovery owns that lifecycle.

### Core plugin rule

Plugins must not require hardcoded plugin-specific logic in core files. If a plugin needs a missing capability, extend the generic plugin surface with a hook or context method instead.

---

## Skills

Hermes has two skill directories:

- `skills/`: built-in skills shipped with the repo and loadable by default.
- `optional-skills/`: heavier or niche skills installed explicitly.

Skill metadata lives in `SKILL.md` frontmatter. Standard fields include:

```yaml
name: ...
description: ...
version: ...
author: ...
license: ...
platforms: [linux, macos]
metadata:
  hermes:
    tags: [...]
    category: ...
    related_skills: [...]
    config: {...}
```

### Skill authoring standards

New or modernized skills should follow these standards:

1. Keep `description` short, concrete, and non-marketing.
2. Reference native Hermes tools by name in prose when describing agent actions.
3. Do not present shell utilities as the primary interaction surface when Hermes has a native tool wrapper.
4. Audit `platforms:` against actual script imports and OS-specific behavior.
5. Credit the human contributor first.
6. Use the modern section order:
   - `# <Skill> Skill`
   - `## When to Use`
   - `## Prerequisites`
   - `## How to Run`
   - `## Quick Reference`
   - `## Procedure`
   - `## Pitfalls`
   - `## Verification`
7. Put scripts in `scripts/`, references in `references/`, and templates in `templates/`.
8. Add tests under `tests/skills/test_<skill>_skill.py`.
9. Skill tests must not make live network calls.
10. `.env.example` edits should be isolated to the skill's own clearly delimited block.

When reviewing external skill PRs, load the dedicated salvage checklist before polishing the contribution.

---

## Curator

The curator manages lifecycle state for agent-created skills. It can mark skills stale and archive them, but users should not lose skills: archives remain restorable.

Important invariants:

- Curator only touches skills with agent-created provenance.
- Bundled and hub-installed skills are off-limits.
- Pinned skills are exempt from auto-transition and LLM review.
- Patching or editing pinned skills is allowed; deletion should be refused.

---

## Delegation

`delegate_task` creates isolated subagents with their own context and terminal session. The parent waits for the child summary before continuing.

Shapes:

- Single task: `goal`, optional context, optional toolsets
- Batch: `tasks: [...]`, each running concurrently up to the configured limit

Roles:

- `leaf`: focused worker with restricted tools
- `orchestrator`: may spawn child workers when enabled and within depth limits

Delegation is synchronous and not durable. For work that must outlive the current turn, use cron or a background terminal process with completion notification.

---

## Cron

Cron jobs live under `cron/` and are user-facing through `hermes cron <verb>` and the `/cron` slash command.

Supported schedule shapes include:

- Durations: `30m`, `2h`, `1d`
- Every phrases: `every 2h`, `every monday 9am`
- Five-field cron expressions: `0 9 * * *`
- ISO timestamps for one-shot jobs

Important invariants:

- Cron sessions have a hard interrupt limit.
- A file lock prevents duplicate scheduler ticks across processes.
- Cron sessions skip memory by default.
- Cron deliveries are not mirrored into the target gateway session; they use their own cron session framing.

---

## Kanban

Kanban is a durable SQLite-backed multi-agent work queue. Users operate it through `hermes kanban <verb>`. Dispatcher-spawned workers receive a dedicated kanban toolset.

Important invariants:

- The board is the hard isolation boundary.
- Tenant is a soft namespace within a board.
- Workers should only see the board they were spawned for.
- Repeated task failures should block the task rather than spin indefinitely.

Do not expose kanban worker-only tools outside the intended execution context unless the platform explicitly enables them.

---

## Skin and Display System

The skin engine lives in `hermes_cli/skin_engine.py` and is data-driven. Skins should be pure data, not code.

Skins customize banner colors, response boxes, spinner faces and verbs, tool prefixes, per-tool emojis, prompt symbols, and branding text.

User skins live under the active Hermes home, typically in `skins/<name>.yaml`.

Do not add new interactive menus using `simple_term_menu`. Use the curses UI helpers instead.

Do not use ANSI erase-to-end-of-line (`\033[K`) in spinner or display code under `prompt_toolkit`; use explicit space padding.

---

## Dependency Policy

All dependencies must have upper bounds or exact pins, depending on source type.

| Source type | Required treatment | Example |
|---|---|---|
| PyPI package | Floor plus upper bound | `httpx>=0.28.1,<1` |
| Pre-1.0 PyPI package | Floor plus narrow minor ceiling | `pkg>=0.29,<0.32` |
| Git URL | Commit SHA | `git+https://...@<40-char-sha>` |
| GitHub Action | Commit SHA plus comment | `uses: actions/checkout@<sha>  # v4` |
| CI-only pip install | Exact version | `pyyaml==6.0.2` |

When adding a dependency:

1. Add a bounded requirement.
2. Regenerate the lockfile with hashes.
3. Do not commit bare lower bounds such as `>=1.2.3` without a ceiling.

---

## Testing

Always use `scripts/run_tests.sh` for repo tests unless the wrapper is unavailable or the task explicitly requires raw pytest.

```bash
scripts/run_tests.sh
scripts/run_tests.sh tests/gateway/
scripts/run_tests.sh tests/agent/test_foo.py::test_x
scripts/run_tests.sh -v --tb=long
scripts/run_tests.sh --no-isolate tests/foo/   # debugging only; disables subprocess isolation
```

The wrapper keeps local behavior aligned with CI by controlling credentials, home directory, timezone, locale, xdist behavior, and the in-tree subprocess-isolation plugin.

### Subprocess-per-test isolation

Tests run in freshly spawned Python subprocesses through `tests/_isolate_plugin.py`. This prevents module globals, ContextVars, and other process state from leaking across tests.

Important details:

- The plugin uses `multiprocessing.get_context("spawn")`, not POSIX `fork`, so it works across Linux, macOS, and Windows.
- `isolate_timeout` in `pyproject.toml` caps each isolated test.
- `--no-isolate` disables isolation for focused debugging only.
- The plugin disables itself in child processes with `HERMES_ISOLATE_CHILD=1` to avoid recursive spawning.

Do not rely on raw `pytest` unless the wrapper is unavailable. If raw pytest is unavoidable, activate the venv and run:

```bash
python -m pytest tests/ -q
```

For focused debugging without isolation:

```bash
python -m pytest tests/agent/test_foo.py -q --no-isolate
```

### Test design

Do not write change-detector tests. A change-detector fails when ordinary data changes, such as model catalogs, provider lists, config version literals, or enumeration counts.

Bad tests snapshot current data:

```python
assert "specific-new-model" in _PROVIDER_MODELS["provider"]
assert DEFAULT_CONFIG["_config_version"] == 21
assert len(_PROVIDER_MODELS["huggingface"]) == 8
```

Good tests assert behavior or invariants:

```python
assert "provider" in _PROVIDER_MODELS
assert len(_PROVIDER_MODELS["provider"]) >= 1
assert raw["_config_version"] == DEFAULT_CONFIG["_config_version"]

for model in _PROVIDER_MODELS["huggingface"]:
    assert model.lower() in DEFAULT_CONTEXT_LENGTHS_LOWER
```

Tests must not write to the real Hermes home. The autouse test fixture should isolate `HERMES_HOME`; any code that hardcodes `~/.hermes` bypasses that protection and must be fixed.

---

## Common Change Recipes

### Add a core tool

1. Implement `tools/<tool>.py`.
2. Register it with `tools.registry.registry.register(...)`.
3. Return JSON strings from handlers.
4. Add it to the appropriate toolset in `toolsets.py`.
5. Use `get_hermes_home()` for state and `display_hermes_home()` for user-facing paths.
6. Add focused tests through the wrapper.

### Add a local or optional tool

Use a plugin instead of editing core:

```text
$HERMES_HOME/plugins/<name>/plugin.yaml
$HERMES_HOME/plugins/<name>/__init__.py
```

Register the tool through the plugin context.

### Add a slash command

1. Add a `CommandDef` in `hermes_cli/commands.py`.
2. Add CLI dispatch in `cli.py`.
3. Add gateway dispatch only if the command should work over messaging platforms.
4. Keep prompt-cache implications explicit.

### Add a config setting

1. Add the key to `DEFAULT_CONFIG`.
2. Decide whether a migration is actually required.
3. Update the relevant loader path if gateway behavior is involved.
4. Keep non-secrets out of `.env`.

### Add a skill

1. Choose `skills/` only for broadly useful built-ins.
2. Choose `optional-skills/` for heavy, niche, or dependency-heavy capabilities.
3. Follow modern `SKILL.md` structure.
4. Include helper scripts for non-trivial logic.
5. Add no-network tests.

### Change dashboard chat behavior

Do not rebuild chat in React. Extend the Ink TUI or the TUI gateway so dashboard behavior follows automatically.

---

## Known Pitfalls Checklist

Before finishing a change, check the relevant items:

- [ ] No hardcoded `~/.hermes` runtime paths.
- [ ] User-facing Hermes paths use `display_hermes_home()`.
- [ ] State paths use `get_hermes_home()`.
- [ ] Gateway changes handle active-session control commands correctly.
- [ ] Tool schema descriptions do not recommend unavailable cross-tool calls.
- [ ] New tools are both registered and included in a toolset.
- [ ] Tool handlers return JSON strings.
- [ ] Plugins do not hardcode plugin-specific behavior into core.
- [ ] Model-provider plugins use their own lazy discovery path.
- [ ] Prompt-cache-sensitive slash commands defer changes unless immediate invalidation is explicit.
- [ ] Dashboard changes do not duplicate the TUI chat surface.
- [ ] Display/spinner code avoids `\033[K`.
- [ ] `_last_resolved_tool_names` in `model_tools.py` is treated as process-global state and not trusted blindly during delegation.
- [ ] New interactive menus use curses helpers, not `simple_term_menu`.
- [ ] Tests use `scripts/run_tests.sh`.
- [ ] Tests assert behavior or invariants, not volatile snapshots.
- [ ] Tests do not touch the real Hermes home.
- [ ] Dependencies have ceilings, exact pins, or commit SHAs as required.
- [ ] Before squash-merging stale branches, update against `main` first and verify the final diff. Stale branch squashes can silently revert unrelated recent fixes.

---

## Final Rule

When in doubt, preserve the architecture boundary.

Hermes works because tools, toolsets, plugins, skills, providers, profiles, gateway adapters, the TUI, and the dashboard each have distinct responsibilities. Most serious regressions come from crossing those boundaries casually. Make the boundary explicit, change the narrowest surface, test through the real path, and leave the system easier to reason about than you found it.
