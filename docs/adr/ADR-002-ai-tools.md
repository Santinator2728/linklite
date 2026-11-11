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
    config.yaml    # model version, temperature, max tokens, thresholds
```

**Reproducibility check (P2):** the same gate is run twice on the same commit with the same configuration, and both decisions are compared and documented. To make the decision as stable as possible: temperature 0, a structured output format, and a decision based on a threshold rather than on free text.

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
