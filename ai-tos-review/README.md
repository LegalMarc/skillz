# ai-tos-review

A rapid, **IP-focused** review of an AI tool's Terms of Service, built for corporate adoption decisions. It answers the only two questions that usually gate a go/no-go:

1. Can the provider **train on / reuse** the data we put in?
2. Do we **own the outputs**?

It returns a one-line verdict, a short employee-facing findings list, and a citation-backed addendum a lawyer can act on. It is intentionally narrow — **not** a privacy, information-security, or general commercial-terms review — and it says so in its own output.

> ⚖️ This produces a **first-pass triage**, not legal advice. Every verdict routes to human legal review.

## Why this exists, and how I use it

*From the author — a corporate legal perspective:*

This skill is built for **standard, non-negotiable terms of service** — the click-through kind where we have no negotiating leverage. The decision is up-or-down: take the agreement as written or find a different product. That framing is why the skill focuses **solely on IP matters** and deliberately ignores liability caps, indemnities, warranty disclaimers, and the other general terms that may be unfavorable but are take-it-or-leave-it. Those terms create risks we can insure against or live with. IP risk is different: if a vendor can train on our data, or we don't own what the tool generates, that risk can be **existential** — and it needs to be carefully understood before green-lighting any AI-based tool for internal use at our company.

Here's how it works in practice. Our legal department policy is that when you submit a legal ticket for review of a service's terms **that include an AI feature**, you are required to **first run this skill on the terms of service and include its output in the ticket**. That does two things:

1. **It gives you an early heads-up.** If the terms are quite bad, you'll know before legal ever sees them — which may encourage you to find a different, suitable product and save the legal review entirely, because you never submit the ticket.
2. **It accelerates the attorney's review.** The reviewing attorney can double-check the most important terms quickly, because the skill has already found them, told you where they are, and quoted them.

The skill's output is a triage, not a clearance — every verdict, including the favorable ones, routes to a human attorney. But it moves the easy kills out of the queue and hands the hard ones over pre-digested.

## What makes it portable

The whole skill is a single self-contained prompt in [`SKILL.md`](SKILL.md), written to be **model-neutral**. It runs the same way on any high-effort SOTA model (GPT-5.5+, Claude Opus, etc.). There are no tool calls, no runtime assumptions, and the operative content is not split across files — so the body pastes cleanly into surfaces that don't load skill files.

Keeping it in one file is also what Anthropic's [skill-authoring guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) recommends here: split a skill only when it serves *different* trigger patterns or has sections that apply to only some triggers, and keep the body under 500 lines. This skill has one trigger and every line runs every time, so a single body is the best-practice shape — and it happens to give us the paste-portability the deployment targets need.

## Configure before first use

Open `SKILL.md` and set the config block near the top:

| Setting | Default | What it does |
|---|---|---|
| `OUTPUT_MODE` | `email` | `email` = one paste-into-email block; `structured` = on-screen headings/lists |
| `WE` / `US` / `OUR` | generic first person | Replace only if you want branded output |
| `ROUTING_ACCEPTABLE` | submit-to-legal wording | Clause appended to acceptable/borderline verdicts |
| `ROUTING_NOT_ACCEPTABLE` | submit-to-legal wording | Clause appended to the does-not-meet verdict |

## Deploy it

### Claude Code / Codex (agent runtimes)
The `SKILL.md` frontmatter auto-triggers the skill when someone asks to review an AI tool's ToS for IP risk. Drop the `ai-tos-review/` directory into your skills location (or symlink it). No extra steps.

### Claude Project or ChatGPT Custom GPT / Project
These surfaces don't read `SKILL.md` frontmatter — you paste the prompt instead:

1. Copy **everything in `SKILL.md` below the `---` frontmatter block** (from `# AI Tool ToS — IP Risk Review` to the end).
2. Paste it into the project's **custom instructions** (ChatGPT: *Instructions*; Claude: *Project instructions* / *custom instructions*).
3. Start a chat and paste the ToS. For a one-off, you can instead paste the same body as the first message, then the ToS as the second.

### Any chat, ad hoc
Paste the body, then the ToS, in a single conversation. Use a high-effort/reasoning setting for best results.

## Usage tips

- **Feed it the whole agreement.** If the ToS references a **DPA**, **enterprise terms**, or a **training/opt-out policy**, provide those too — the skill will otherwise flag the gap and grade conservatively.
- **URLs:** paste the actual text. If the model can't reliably retrieve a link, the skill will ask for the text rather than guess.
- **Two output modes:** keep `email` for pasting verdicts into a ticket/email; switch to `structured` when reading on screen or embedding in a doc.

## Testing

The skill ships with a runnable evaluation set in [`evals/`](evals/) — three fixture ToS documents that span the decision space, each paired with objectively checkable `expected_behavior`:

| Eval | Fixture | Exercises |
|---|---|---|
| `clean-accept-email-mode` | `acme-acceptable.md` | Clear accept; strong-positive findings; ignore-list adherence; email formatting |
| `clear-reject-structured-mode` | `dataforge-adverse.md` | Broad-training + provider-owned outputs reject; the fixed-penalty exception; `structured` mode toggle |
| `borderline-missing-dpa` | `nimbus-borderline.md` | Borderline verdict; opt-out warning; catching a referenced-but-missing DPA |

To evaluate, load the skill, run each `query` against its `files`, and check the output against `expected_behavior`. Per Anthropic's guidance, **build/extend these evals before adding more instructions** — they're the source of truth for whether a change helps. Test on every model you deploy to (the design target is GPT-5.5+ and Claude Opus at high effort).

## How it decides (verdict rubric)

Two axes → four verdicts:

|                        | Outputs **Ours** | Ownership **Ambiguous** | Outputs **Not ours** |
|------------------------|------------------|-------------------------|----------------------|
| Training **Protected** | ✅ Acceptable    | 🟡 Borderline           | ❌ Does not meet      |
| Training **Ambiguous** | 🟡 Borderline    | 🟠 Probably not          | ❌ Does not meet      |
| Training **Adverse**   | ❌ Does not meet | ❌ Does not meet         | ❌ Does not meet      |

*Training Protected* includes a clean opt-out you complete before use. See `SKILL.md` for the full checklist of what's reviewed and what's deliberately ignored.
