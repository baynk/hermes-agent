# Ryan live Hermes architecture snapshot

Last verified: 2026-05-20T22:47:38Z on Ryan's live Ubuntu VPS.

This is a human map of the current Hermes/Ava setup. It is intentionally operational, not marketing copy. It answers: where the files live, what the brain is, which agents exist, which models they use, where voice is configured, and where to look when the system changes again.

## One-screen overview

- **Source checkout:** `/home/ubuntu/hermes-agent`
- **Runtime home:** `/srv/hermes/data`
- **Main personality file:** `/srv/hermes/data/SOUL.md`
- **Repo copy of default SOUL template:** `/home/ubuntu/hermes-agent/docker/SOUL.md`
- **Main runtime config:** `/srv/hermes/data/config.yaml`
- **Main memory/data workspace:** `/srv/hermes/data`
- **Profiles/sub-agents:** `/srv/hermes/data/profiles/<profile-name>/`
- **Skills:** `/srv/hermes/data/skills/` plus repo-bundled `skills/` and `optional-skills/`
- **Logs:** `/srv/hermes/data/logs/`
- **Kanban DB:** `/srv/hermes/data/kanban.db`
- **Gateway/chat entrypoint:** Hermes gateway service, connected to Telegram and Discord in normal operation
- **Dashboard app port:** `127.0.0.1:9120` in the current live deployment notes
- **Dashboard auth proxy:** `127.0.0.1:9119` in the current live deployment notes

## Mental model

Hermes is not one bot file. It is a runtime made of five layers:

1. **Core agent loop** — `run_agent.py` owns the LLM conversation loop. It builds messages, calls the configured model, executes tools, appends tool results, and continues until it has a final answer or hits its iteration budget.
2. **Tool registry** — tool files register themselves through `tools/registry.py`. `model_tools.py` discovers tools and dispatches tool calls. `toolsets.py` groups tools into enabled/disabled bundles like `terminal`, `file`, `web`, `browser`, `tts`, `delegation`, and `cronjob`.
3. **Gateway/session layer** — `gateway/` adapts Telegram, Discord, API server, and other platforms into Hermes sessions. This is why Ava can answer from Telegram while using the same underlying agent machinery as the CLI.
4. **Runtime home** — `/srv/hermes/data` is Ryan's live state: config, memory, skills, profiles, logs, auth pools, cron output, Kanban board, and workspace files. This is the important operational brain, not just the Git checkout.
5. **Profiles/Kanban workers** — profile directories under `/srv/hermes/data/profiles/` are isolated sub-agent identities. Kanban can dispatch work to these profiles as durable workers.

## Request flow

A typical Telegram/Discord message flows like this:

1. Platform adapter receives the message under `gateway/platforms/`.
2. Gateway resolves the chat/thread/session and loads the active runtime context from `/srv/hermes/data`.
3. Hermes builds the system prompt from persona, project context, memories, skills, platform rules, and enabled toolsets.
4. `AIAgent.run_conversation()` in `run_agent.py` calls the configured model.
5. If the model requests tools, `model_tools.py` dispatches them and returns JSON/tool output back into the conversation.
6. If work is delegated, `delegate_task` creates bounded child agents; if work is durable, Kanban dispatches profile workers from `/srv/hermes/data/profiles/`.
7. Final text/media is returned through the platform adapter.
8. Session state and logs are written under `/srv/hermes/data`.

## Current main model and behavior

Live config verified from `/srv/hermes/data/config.yaml`:

- **Provider:** `openai-codex`
- **Default model:** `gpt-5.5`
- **Runtime selector:** `model.openai_runtime: auto`
- **Main max turns:** `agent.max_turns: 60`
- **Gateway timeout:** `agent.gateway_timeout: 1800`
- **Reasoning effort:** `agent.reasoning_effort: medium`
- **Tool-use enforcement:** `agent.tool_use_enforcement: auto`
- **Service tier:** `priority`

Delegation config:

- **Child model/provider:** blank, so children inherit/resolve from runtime defaults unless explicitly overridden.
- **Max child iterations:** `50`
- **Max concurrent children:** `3`
- **Max spawn depth:** `1`
- **Default child toolsets:** `terminal`, `file`, `web`
- **Orchestrator enabled:** `true`
- **Subagent auto-approve:** `false`

## Current profile roster

These profile directories currently exist under `/srv/hermes/data/profiles/`.

Active configured profiles:

- **analyst** — `openai-codex / gpt-5.5`; tools: `web`, `file`, `skills`, `session_search`, `memory`, `clarify`, `kanban`
- **backend-eng** — `openai-codex / gpt-5.5`; tools include `web`, `terminal`, `file`, `code_execution`, `todo`, `kanban`
- **brand-writer** — `openai-codex / gpt-5.5`; tools: `web`, `file`, `skills`, `session_search`, `memory`, `clarify`, `kanban`
- **claude-eng** — `openai-codex / gpt-5.5`; tools include `web`, `terminal`, `file`, `code_execution`, `todo`, `kanban`
- **codex-eng** — `openai-codex / gpt-5.5`; tools include `web`, `terminal`, `file`, `code_execution`, `todo`, `kanban`
- **doc-writer** — `openai-codex / gpt-5.5`; tools: `file`, `skills`, `session_search`, `memory`, `clarify`, `kanban`
- **engineer** — `openai-codex / gpt-5.5`; tools include `web`, `terminal`, `file`, `code_execution`, `todo`, `kanban`
- **frontend-eng** — `openai-codex / gpt-5.5`; tools include `web`, `browser`, `vision`, `terminal`, `file`, `code_execution`, `todo`, `kanban`
- **ops** — `openai-codex / gpt-5.5`; tools include `web`, `browser`, `terminal`, `file`, `code_execution`, `todo`, `cronjob`, `kanban`
- **orchestrator** — `openai-codex / gpt-5.5`; tools: `skills`, `todo`, `memory`, `session_search`, `clarify`, `kanban`
- **orchestrator-hermes** — `openai-codex / gpt-5.5`; tools: `web`, `browser`, `file`, `skills`, `session_search`, `memory`, `clarify`, `kanban`
- **planner** — `openai-codex / gpt-5.5`; tools include `web`, `file`, `todo`, `kanban`
- **pm** — `openai-codex / gpt-5.5`; tools include `web`, `file`, `todo`, `kanban`
- **researcher** — `openai-codex / gpt-5.5`; tools: `web`, `browser`, `file`, `skills`, `session_search`, `memory`, `clarify`, `kanban`
- **researcher-opus** — `claude-code / claude`; tools: `web`, `browser`, `file`, `skills`, `session_search`, `memory`, `clarify`, `kanban`
- **reviewer** — `openai-codex / gpt-5.5`; tools include `web`, `browser`, `vision`, `terminal`, `file`, `code_execution`, `kanban`
- **verifier** — `openai-codex / gpt-5.5`; tools include `web`, `browser`, `vision`, `terminal`, `file`, `code_execution`, `kanban`
- **writer** — `openai-codex / gpt-5.5`; tools: `web`, `file`, `skills`, `session_search`, `memory`, `clarify`, `kanban`

Profile directories that currently exist but showed no explicit model/provider in their `config.yaml` during this check:

- `copy-refiner-opus`
- `default`
- `designer`
- `designer-opus`
- `implementer-codex`
- `researcher-gemini`
- `researcher-grok`
- `reviewer-verifier`

That does not necessarily mean they are useless. It means the profile directory exists but the inspected config did not declare an explicit model/provider. Treat them as needing cleanup or verification before relying on them.

## Kanban workers

Verified with `HERMES_HOME=/srv/hermes/data hermes kanban assignees`:

- **orchestrator** — on disk, idle
- **researcher** — on disk, has completed work
- **analyst** — on disk, idle
- **brand-writer** — on disk, has completed work
- **writer** — on disk, idle
- **doc-writer** — on disk, idle
- **designer** — listed, but Kanban reported `ON DISK: no` even though a `/srv/hermes/data/profiles/designer/` directory exists; verify before dispatching work there
- **engineer** — on disk, has one blocked item
- **ops** — on disk, idle
- **verifier** — on disk, idle

Current board:

- **Board:** `default`
- **Counts at verification:** `archived=2`, `blocked=1`, `done=2`

Useful commands:

```bash
HERMES_HOME=/srv/hermes/data hermes kanban boards list
HERMES_HOME=/srv/hermes/data hermes kanban assignees
HERMES_HOME=/srv/hermes/data hermes kanban list --json
HERMES_HOME=/srv/hermes/data hermes kanban show TASK_ID --json
```

## Enabled main toolsets

Verified with `HERMES_HOME=/srv/hermes/data hermes tools list`.

Enabled in the main CLI/runtime view:

- `web`
- `browser`
- `terminal`
- `file`
- `code_execution`
- `vision`
- `image_gen`
- `x_search`
- `tts`
- `skills`
- `todo`
- `memory`
- `session_search`
- `clarify`
- `delegation`
- `cronjob`
- `messaging`
- `computer_use`

Disabled in that view:

- `video`
- `video_gen`
- `moa`
- `homeassistant`
- `spotify`
- `yuanbao`

Note: tool availability is profile/platform-specific. After changing tool config, start a fresh session/reset; tool schemas are not safely mutated mid-conversation because of prompt caching.

## Voice: where it is configured and stored

Voice has two separate parts: STT for incoming voice messages and TTS for generated audio replies.

Live config from `/srv/hermes/data/config.yaml`:

- **STT enabled:** `true`
- **STT provider:** `local`
- **Local STT model:** `base`
- **OpenAI fallback/configured model:** `whisper-1`
- **Mistral fallback/configured model:** `voxtral-mini-latest`
- **TTS provider:** `edge`
- **Edge TTS voice:** `en-US-AriaNeural`
- **OpenAI TTS configured model:** `gpt-4o-mini-tts`
- **OpenAI TTS configured voice:** `alloy`
- **xAI TTS configured voice:** `eve`
- **Voice auto-TTS:** `false`
- **Max recording seconds:** `120`
- **Silence duration:** `3`

Storage paths observed during this check:

- **Generated audio cache:** `/srv/hermes/data/audio_cache/` exists.
- **Logs:** `/srv/hermes/data/logs/` exists.
- **Voice memos path:** `/srv/hermes/data/voice-memos/` did not exist at verification time.

Key source locations:

- `tools/tts_tool.py` handles `text_to_speech` behavior.
- `model_tools.py` maps the `tts_tools` group to `text_to_speech`.
- `toolsets.py` defines the `tts` toolset.
- Gateway platform adapters handle whether an audio file is sent as native audio/voice or as a regular attachment.

## Where SOUL.md is

The main live personality file is:

```bash
/srv/hermes/data/SOUL.md
```

There is also a repository template/copy at:

```bash
/home/ubuntu/hermes-agent/docker/SOUL.md
```

The workspace rules under `/srv/hermes/data/AGENTS.md` say every session should read:

1. `SOUL.md`
2. `USER.md`
3. today's and yesterday's daily memory notes
4. `memory/INDEX.md`
5. `MEMORY.md` for the main session
6. recent lessons and project registry

So if Ryan asks “where is Ava's personality / soul file,” the live answer is `/srv/hermes/data/SOUL.md`, not only the repo template.

## Memory and continuity

Important runtime memory locations under `/srv/hermes/data`:

- `MEMORY.md` — curated executive summary for the main session
- `USER.md` — durable profile of Ryan
- `memory/YYYY-MM-DD.md` — daily working memory/logs
- `memory/INDEX.md` — index of typed memories
- `memory/preferences/`, `memory/lessons/`, `memory/projects/`, etc. — typed memory files
- `sessions/` or session DB locations depending on current storage backend — searchable through `session_search` / `hermes sessions`

Operational rule: do not treat the Git repo as the whole brain. The live brain is the combination of code in `/home/ubuntu/hermes-agent` plus runtime state in `/srv/hermes/data`.

## Source-code orientation

The highest-leverage source files/directories:

- `run_agent.py` — core `AIAgent` loop and tool-calling lifecycle
- `model_tools.py` — tool discovery and tool call dispatch
- `toolsets.py` — toolset definitions
- `cli.py` — interactive CLI orchestration
- `hermes_cli/commands.py` — central slash-command registry
- `hermes_cli/config.py` — default config and schema-ish defaults
- `hermes_constants.py` — `get_hermes_home()` and profile-aware path resolution
- `gateway/` — Telegram/Discord/API server adapters and gateway sessions
- `cron/` — scheduled jobs
- `plugins/kanban/` — Kanban board/worker machinery
- `tools/` — individual tool implementations
- `skills/` and `optional-skills/` — repo-bundled procedural knowledge
- `web/` — Vite dashboard frontend
- `hermes_cli/web_dist/` — built dashboard assets served by the CLI/dashboard
- `tests/` — pytest suite

## Operational commands Ryan should know

```bash
# Confirm active config paths
HERMES_HOME=/srv/hermes/data hermes config path
HERMES_HOME=/srv/hermes/data hermes config env-path

# See models/profiles/tools
HERMES_HOME=/srv/hermes/data hermes profile list
HERMES_HOME=/srv/hermes/data hermes tools list
HERMES_HOME=/srv/hermes/data hermes status --all

# Inspect Kanban workers
HERMES_HOME=/srv/hermes/data hermes kanban assignees
HERMES_HOME=/srv/hermes/data hermes kanban boards list
HERMES_HOME=/srv/hermes/data hermes kanban list --json

# Check service health on the live VPS
python /srv/hermes/data/scripts/service_health.py

# Follow logs
HERMES_HOME=/srv/hermes/data hermes logs --follow
```

## Documentation maintenance rule

Update this file after any change that affects:

- default model/provider
- profile roster
- Kanban worker roles
- delegation settings
- voice/STT/TTS provider
- runtime paths
- dashboard/gateway topology
- major toolset availability

If it is not in this file or in `AGENTS.md`, assume Ryan will not remember it next week.
