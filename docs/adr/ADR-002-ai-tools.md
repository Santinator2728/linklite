# ADR-002: AI tools for development and for the pipeline

- **Status:** Accepted
- **Date:** 22 October 2026
- **Jira:** XP-24
- **Decider:** Santiago Guerrero (Product Owner, Sprint 2)

## Context

The project brief sets two AI-related requirements:

1. **Hard restriction:** the team must adopt at least one AI-based tool to support programming and code development.
2. **Expected outcome:** the CI/CD pipeline must include AI-augmented quality gates, and the configuration of each gate (prompt template, model version, parameters, thresholds) must be version-controlled and checked for reproducibility (Ops Pattern P2, from Sprint 3).

Constraints: one developer with about 6 hours per sprint, a public GitHub repository, and a tight budget (free tiers or low pay-per-use cost).

## Decision 1 – AI tool for development: Claude Code

**Options considered**

| Option | Strengths | Weaknesses |
|---|---|---|
| GitHub Copilot | Inline completion inside the editor | Works mostly line by line; little help with multi-file tasks, CI or Jira |
| ChatGPT / Claude in the browser | Good explanations | Copy-paste workflow; no access to the repository, terminal or Jira |
| **Claude Code (chosen)** | Agent that reads the repository, runs commands (tests, linters, `gh`), edits files and works with Jira through MCP | Can produce a lot of code quickly, so every change must still be reviewed and understood by the developer |

**Why:** with very little time, the biggest gain comes from a tool that can carry a whole task end to end: write the code and the tests, run them, read the CI logs and update Jira. Claude Code does that inside the real environment.

**How it is used (rules)**

- Every change goes through a pull request and the full pipeline; nothing reaches `main` without passing the gates.
- The developer reviews and must be able to explain every change before merging (the Sprint Review presentations depend on it).
- Code commits made with Claude Code carry a `Co-Authored-By: Claude` trailer, so AI-assisted code is traceable. Documentation is written and owned by the developer; how AI was used is disclosed in this ADR and in the final report.
- AI output is never used to fabricate project evidence (Jira records reflect real dates and real work).

## Decision 2 – AI-augmented gate in the pipeline: LLM code review (Sprint 3)

An LLM review step will run on every pull request. It reads the diff and returns a structured verdict (for example JSON with `decision: pass|fail`, findings and severity), and the pipeline fails when the verdict breaks the threshold.

**Model:** Claude through the Anthropic API, pinned to an exact model version (no "latest" alias), so that a model update cannot silently change the gate's behaviour.

**Versioned configuration (for P2)**, stored next to the code:

```
ai-gates/
  code-review/
    prompt.md      # prompt template
    config.yaml    # model version, effort, max tokens, threshold
```

**Reproducibility check (P2):** the same gate is run twice on the same commit with the same configuration, and both decisions are compared and documented. To make the decision as stable as possible: a fixed model version, a structured output format, and a decision based on a threshold rather than on free text. (The first version of this ADR also said "temperature 0"; see the update below.)

**Why an LLM review and not only rule-based tools:** Semgrep and SonarCloud catch known patterns. An LLM review can point out design problems that rules do not express (unclear responsibilities, missing validation on a new endpoint, a change that breaks a contract between services). It complements the deterministic gates; it never replaces them.

## Limitations and ethical considerations

- **Non-determinism:** the same prompt can produce different answers. This is exactly what P2 measures, and it is why the AI gate must not be the only security gate.
- **Over-reliance:** generated code can look right and still be wrong. Mitigated by tests, deterministic gates and human review of every PR.
- **Data exposure:** the AI gate sends code diffs to an external API. Acceptable here because the repository is public and contains no secrets; secrets are kept in GitHub Secrets and never in the code.
- **Cost:** pay per use. The gate runs only on pull requests and only on the diff, to keep cost low.
- **Authorship and assessment:** AI-assisted work is disclosed (commit trailers, this ADR, the final report's section on AI use).

## Consequences

- Development is faster, but the developer must spend part of the saved time understanding and reviewing the generated work.
- Sprint 3 adds an `ANTHROPIC_API_KEY` secret and the `ai-gates/` folder, and records the P2 reproducibility results in Jira.

## Update – 12 November 2026 (Sprint 3)

The AI code review is now built and is a required check on `main` (Jira XP-36). Three things changed from the plan above:

- **No "temperature 0".** When I built the gate, I found that the current Claude models no longer accept the temperature setting. So I cannot force the model to always pick the most likely answer. Instead, the gate stays stable through the other measures: the model is fixed to one exact version (`claude-opus-5-5`), the answer must follow a fixed JSON format, all settings are saved in `config.yaml`, and my script makes the pass/fail decision from the severity of the findings, not from the AI's text.
- **The gate runs from `main`.** On its first review, the AI found that a pull request could change the gate's own prompt and approve itself. Now the gate always uses the prompt and settings from `main`; changes to them only count after they are merged.
- **The gate is treated as code that handles untrusted input.** It reads data about the pull request and the answer of an external model. Semgrep and SonarCloud found three places where I trusted that data too much (Architectural Feedback Log entry AF-3, Jira XP-44), and they were fixed.

**First P2 result (Jira XP-37):** I ran the gate 5 times on the same commit with the same settings. The decision and the problems found were the same every time; only the wording and one line number changed. I still need to test a borderline change, where the answer is more likely to vary. If it is not stable there, I will run the review three times and use the majority result.
