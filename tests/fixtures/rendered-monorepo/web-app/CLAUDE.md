# web-app — the front end

Local context for this folder only. Conventions and guardrails for the whole
repo are in the root `CLAUDE.md`; nothing here restates them.

Built with **Next**.
It server-renders, so the container runs a Node
process and `next.config.ts` sets `output: "standalone"`.

## Commands

```bash
pnpm install --frozen-lockfile
pnpm run lint          # biome: lint and format in one pass
pnpm run format        # fix formatting rather than arguing with the linter
pnpm run typecheck     # tsc --noEmit
pnpm run test
pnpm run test:coverage
pnpm run build
pnpm run dev
```

Exactly what CI runs, from the versions pinned in `web-tool-versions.txt`.
Coverage is reported on every run and enforced once the repo serves production
(DES §11).

## Guardrails

- **NEVER put a secret in `NEXT_PUBLIC_*`
  or anywhere the bundler inlines.** It ships to every browser and is readable
  with view-source. A browser cannot keep a secret; the API it calls holds the
  credential.
- **NEVER add a package to `onlyBuiltDependencies` to make an install work.**
  That list is what stops a dependency running arbitrary code on install
  (DES §6). If something new needs it, say why in the pull request.
- **NEVER raise a single `@vitest/*` pin by hand.** They move together, and a
  mismatched one resolves to a version pnpm's release-age policy then rejects.
- **NEVER disable `strict` in TypeScript, or add `any` to silence an error.**
  Both are the gate doing its job.
