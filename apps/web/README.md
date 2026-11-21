# agrodesk-web

Next.js 15 (App Router) PWA for Agrodesk dealers.

## Run locally

```bash
pnpm install         # or npm/yarn
cp .env.example .env
pnpm dev             # http://localhost:3000, expects API on :8000
```

## Styling

Tailwind + shadcn/ui is set up (see `components.json`). To add components your
team chose at scaffold time, run inside this folder:

```bash
npx untitledui@latest init . --nextjs      # merges Untitled UI tokens / baseline
npx shadcn@latest add button input card dialog form badge  # fills the primitives we use
npx shadcn@latest add @react-bits/SplitText-JS-CSS          # animation accents
```

The minimal primitives in `src/components/ui/*` ship with this repo so the app
runs **before** those commands are executed; shadcn add will overwrite them.

## i18n (scaffold only in E3)

`next-intl` will land in E3.1 with Marathi + Hindi catalogs.

## Offline queue

Deferred to E3.1 — the service worker is registered but holds no cache.
