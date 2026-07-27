<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

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
