# Maintaining the public email triage skill

The public repository distributes generic source and synthetic tests. Mailbox configuration, personal rules, message files, histories and run reports stay local/private.

## Local profile

Setup defaults to `ignored-resources/email-triage/local-config.json` at the repository root. Personal rules live beside it as `rules.md`, or at the private configuration's explicit `rules_path`. Run `python3 email-triage/scripts/config.py` to see effective file paths. Legacy local configuration and explicit `EMAIL_TRIAGE_CONFIG` remain supported. Never force-add ignored profiles.

## Publish an update

1. Fetch the public repository and prepare a clean worktree from its current main. Review any remote changes before exporting; keep unrelated work untouched.
2. From the canonical skill directory (the one containing `SKILL.md`), export its reviewed file lists into that worktree with `python3 scripts/package_skill.py --directory /path/to/public-worktree/email-triage`. Runtime files and synthetic test files are explicitly listed in `package-files.json`; generic rules replace personal rules. Export does not commit, push, or copy private Git history.
3. From the public repository root, run the synthetic suite with `EMAIL_TRIAGE_CONFIG=/path/to/nonexistent-profile.json python3 -m unittest discover -s email-triage/tests`. Inspect the exact Git diff, every newly added file, and the public file list. Keep setup/help accurate when capabilities change. Never stage actual mailbox reports or private profiles.
4. Commit only the reviewed public paths and push the public branch. Check its CI result. Prefer a GitHub no-reply author address for public commits. The GitHub repository is the normal sharing link; an archive remains optional.

The CI suite uses fabricated fixtures and no configured mailbox. Browser fixtures can be checked locally using [the browser test guide](../tests/browser/README.md). Mechanical tests do not establish production email-classification accuracy or complete live Mail behavior.
