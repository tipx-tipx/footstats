<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

# Two access levels — check before you show anything

`APP_PASSWORD` = admin (full view). `KLIENT_PASSWORD` = external client
(product only, no model internals). The second is **optional** — unset, the app
behaves exactly as before, one password, everyone is admin.

Role lives in the session cookie and is covered by the signature, so editing it
does not escalate — `npm run test:role` proves it (9 checks, no framework).

**Hiding something in the UI is not hiding it.** `SkutecznoscScena` is a client
component, so anything passed in props ends up in the page source even when
nothing renders it. Strip on the server instead — see `lib/okrojDlaKlienta.ts`.
When adding a new panel with model diagnostics, ask first: does the client's
browser need to *receive* this?

# NEVER run `next build` while `next dev` is running

Both write to `.next`. The dev server watches that directory, so a production
build (~350 MB of writes) triggers a storm of file-system events, and Turbopack
re-runs PostCSS in a **separate node process** for each one. Measured
2026-07-27: **1936 node processes, 14 GB RAM**, on a project with exactly one
CSS file. It nearly took the machine down.

- `npm run build` now refuses to start if a dev server is detected
  (`scripts/sprawdz-czy-dev-chodzi.mjs`, wired as `prebuild`).
- To type-check/compile while dev is up: `npm run build:obok` — same build,
  separate `.next-build` directory.
- To clean up stray workers: `npm run stop`.
- Deploy path is untouched: on Vercel/CI the guard exits immediately and
  `next build` writes to `.next` exactly as before.
<!-- END:nextjs-agent-rules -->
