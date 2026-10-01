<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

# Two access levels — check before you show anything

`APP_PASSWORD` = admin (full view). `KLIENT_PASSWORD` = external client
(product only, no model internals). The second is **optional** — unset, the app
behaves exactly as before, one password, everyone is admin.

Role lives in the session cookie and is covered by the signature, so editing it
does not escalate — `npm run test:role` proves it (9 checks, no framework).

**Hiding something in the UI is not hiding it.** Pages render through
`StronaAplikacji` (`app/projekt/_ui/aplikacja/Strona.tsx`), a client component,
so anything passed in props ends up in the page source even when nothing
renders it. Model internals are therefore never *computed* for a client:
`(app)/model/page.tsx` fetches `zKuchnia` and runs `przygotujKontrole()` only
when `czyPelnyWglad(rola)`. `npm run test:role` checks that contract by reading
the page sources. When adding a new panel with model diagnostics, ask first:
does the client's browser need to *receive* this?

# Where the UI lives (redesign, 2026-10)

Real routes (`app/(app)/*`, `app/login`, `error.tsx`, `not-found.tsx`) are thin
server files: fetch raw data (`lib/nowe/surowe.ts`), run the `_dane` adapters
via `zDanymi(surowe, …)`, hand the result to components from `app/projekt/_ui`.
`app/projekt/*` pages are the design workshop (404 in production unless
`POKAZ_PROJEKT=1`) and run the same components on a snapshot. Tokens and
fonts: `app/nowy.css` + Barlow; `globals.css` is only the Tailwind reset.

# Previews and mobile: use the scripts, don't eyeball

- `npm run zrzuty` — Playwright screenshots (laptop + phone) of a production
  build. `npm run zrzuty -- model kupony` for specific routes (leading slash
  optional; Git Bash mangles `/model` into a Windows path).
- `npm run audyt` — finds pages that scroll sideways on a 390 px screen and
  names the element that causes it. Also lists containers that scroll
  horizontally on purpose, so you can judge whether each one has to.

Run `npm run audyt` after any layout change. One decorative element wider than
the viewport makes the whole page swing left-right on a phone, and that is very
hard to spot by looking.

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
