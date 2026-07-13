---
name: pgfaq
description: Answer PostgreSQL core database questions by researching the local postgres source tree, PostgreSQL documentation under doc/src/sgml, relevant source code, and DeepWiki repository knowledge for postgres/postgres; use when the user asks any PostgreSQL database behavior, internals, SQL, configuration, administration, performance, storage, planner, executor, replication, or documentation question and wants a sourced Markdown answer saved to the current project's markdown directory. Refuse questions about non-PostgreSQL-core projects, including PostgreSQL ecosystem plugins, extensions maintained outside postgres/postgres, external tools, drivers, cloud services, forks, or third-party products.
---

# pgfaq

## Scope

Use this skill only for questions about the PostgreSQL core open-source project in `postgres/postgres`.

Refuse the request if it is about a project outside PostgreSQL core, including third-party extensions, plugins, tools, drivers, cloud products, forks, wrappers, or ecosystem projects. State briefly that `pgfaq` only answers PostgreSQL core questions.

## Required Workflow

1. Confirm the current working directory is a PostgreSQL source checkout.
   - Verify expected paths exist, especially `doc/src/sgml`.
   - Prefer `git remote -v`, `git rev-parse --show-toplevel`, and directory checks when needed.
   - If the current directory is not a PostgreSQL source tree, stop and ask the user to run from a postgres source checkout or provide the correct path.

2. Classify the question before researching.
   - Confirm it is within PostgreSQL core scope.
   - Identify likely documentation areas under `doc/src/sgml`.
   - Identify likely source areas, such as `src/backend`, `src/include`, `src/bin`, `src/test`, or `contrib` only when the topic is a PostgreSQL core/contrib module shipped in the postgres repository.

3. Search local documentation and code first.
   - Use `rg` for targeted searches in `doc/src/sgml` and relevant source directories.
   - Read the smallest necessary source and documentation excerpts.
   - Prefer primary PostgreSQL docs and code over memory.
   - Capture exact file paths and line numbers for claims that matter.

4. Ask DeepWiki MCP for repository-grounded context.
   - Use `mcp__deepwiki__ask_question` with `repoName: "postgres/postgres"`.
   - Ask focused questions tied to the user's topic, not broad general prompts.
   - Treat DeepWiki as guidance to cross-check against local code and docs, not as the sole source.

5. Synthesize the answer.
   - Write in Chinese unless the user asks for another language.
   - Make the answer practical and source-backed.
   - Include code/doc references as local paths with line numbers when available.
   - Distinguish confirmed facts from inference.
   - Avoid unsupported advice, folklore, and version claims not backed by the checked source tree or docs.

6. Validate and revise before saving.
   - Send the draft substance to DeepWiki MCP and ask it to check correctness against `postgres/postgres`.
   - Re-check any DeepWiki correction against local docs or source code.
   - Revise the answer when a correction is substantiated.
   - Repeat the DeepWiki validation and local verification loop until no material correctness issues remain or remaining uncertainty is explicitly documented.

7. Save the final answer as Markdown.
   - Ensure the current project has a `markdown` directory; create it if missing.
   - Save the final answer under `markdown/` with a concise, filesystem-safe filename derived from the question.
   - Include a short source section listing the key local docs/code files and DeepWiki checks used.
   - Tell the user the saved file path.

## Answer Format

Use this structure unless the user's requested format clearly conflicts:

```markdown
# <question-title>

## 结论

<direct answer>

## 原理与证据

<explanation grounded in PostgreSQL docs/code>

## 实践建议

<commands, SQL examples, configuration notes, or diagnostic steps when relevant>

## 边界与版本说明

<scope, caveats, source-tree/version limitations, uncertainties>

## 参考来源

- `doc/src/sgml/...`
- `src/...`
- DeepWiki MCP: `postgres/postgres` correctness check
```

## Research Discipline

- Use local PostgreSQL docs and source as the authority.
- Do not answer from memory when code or docs can be checked.
- Do not browse the web unless the user explicitly asks and the answer still stays within PostgreSQL core scope.
- Do not cite DeepWiki as a replacement for local evidence.
- Do not modify PostgreSQL source files while answering.
- Keep changes limited to the generated Markdown file and creating `markdown/` if needed.
