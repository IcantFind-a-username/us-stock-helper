# Repository Skills

This directory vendors the complete local snapshots of the project-related
Agent Skills so a fresh Codex cloud checkout can discover them from
`.agents/skills/`. Supporting scripts, references, assets, agent definitions,
and prompt files are included when present; these are not SKILL.md-only copies.

## Inventory and upstream sources

| Upstream | Vendored skills |
| --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | `brainstorming`, `dispatching-parallel-agents`, `executing-plans`, `finishing-a-development-branch`, `receiving-code-review`, `requesting-code-review`, `subagent-driven-development`, `systematic-debugging`, `test-driven-development`, `using-git-worktrees`, `using-superpowers`, `verification-before-completion`, `writing-plans`, `writing-skills` |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | `frontend-patterns`, `backend-patterns` |
| [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | `karpathy-guidelines` |

`skills-lock.json` preserves the installer metadata available for the two
project-local CLI installations. The other skills are vendored from the
complete local installations available when this snapshot was made.

## Cloud use

After cloning, open the repository root as the Codex workspace. Codex should
discover the skills automatically. Begin by reading:

1. `.agents/skills/using-superpowers/SKILL.md`
2. `.agents/skills/brainstorming/SKILL.md` before creative changes
3. the task-specific skills named in the cloud handoff

Do not treat these files as financial advice. They govern engineering workflow
and coding behavior.

## Update policy

When refreshing a skill, replace the complete skill directory and retain its
relative layout. Review upstream changes before use because skills can contain
instructions and executable scripts. Never commit credentials, local caches,
or Codex system/plugin bundles here.
