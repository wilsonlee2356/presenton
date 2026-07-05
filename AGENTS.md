# AGENTS.md — Presenton

This file is for AI coding agents working on the Presenton repository. It describes the project architecture, build/test workflows, code conventions, and security model as found in the actual source tree. When in doubt, prefer the files referenced here over any general assumption.

---

## Project overview

**Presenton** is an open-source AI presentation generator licensed under Apache 2.0. It can be run in three ways:

1. **Docker / web** — a single container that runs nginx, a Next.js frontend, and a FastAPI backend together.
2. **Electron desktop app** — bundles the same FastAPI backend and Next.js frontend as a native macOS, Windows, and Linux application.
3. **Direct API** — the FastAPI backend can be used standalone as a presentation-generation API.

The repository is **not a monorepo workspace**. It contains three independent `package.json` manifests (root, `servers/nextjs`, `electron`) and one Python project (`servers/fastapi`). Orchestration is done with npm scripts, shell scripts, and `start.js`.

Key top-level files:

- `package.json` — root manifest, mostly manages the closed-source `presentation-export` runtime sync.
- `servers/fastapi/pyproject.toml` — Python backend (FastAPI, SQLModel, Alembic, Mem0, etc.).
- `servers/nextjs/package.json` — Next.js 16 frontend.
- `electron/package.json` — Electron 42 desktop app.
- `start.js` — Docker entrypoint that starts nginx, FastAPI, the MCP server, and Next.js.
- `docker-compose.yml` — production / development / GPU variants.
- `nginx.conf` — reverse proxy inside the container.
- `test-local.sh` — local all-in-one test script.

---

## Technology stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11, FastAPI 0.116, Uvicorn, SQLModel, SQLAlchemy, Alembic |
| **LLM / AI clients** | OpenAI SDK, Google GenAI, LiteLLM-compatible calls, Mem0 OSS, FastEmbed |
| **Documents / export** | `python-pptx`, `pdfplumber`, Pillow, FontTools, `@llamaindex/liteparse`, bundled `presenton-export` runtime, FFmpeg (for MP4 video export) |
| **Databases** | SQLite (`aiosqlite`), PostgreSQL (`asyncpg`/`psycopg`), MySQL (`aiomysql`) |
| **MCP** | `fastmcp` auto-generated from `openai_spec.json` |
| **Frontend** | Next.js 16.2.6, React 19.2.6, TypeScript 5, Tailwind CSS 3.4, Radix UI |
| **Frontend state / editing** | Redux Toolkit, Zod, TipTap, Chart.js, Mermaid, Recharts |
| **Frontend testing** | Node built-in test runner, Cypress (component tests), ESLint 9 |
| **Desktop** | Electron 42.2.0, `electron-builder` 26.8, TypeScript → CommonJS (`app_dist/`) |
| **Runtime / infra** | Node.js 20, npm, nginx, Docker, GitHub Actions |
| **Export / images** | Chromium for Testing, Sharp, ImageMagick, Tesseract OCR |
| **Python packaging** | `uv` (preferred), PyInstaller (`servers/fastapi/server.spec`) |

---

## Repository layout

```
/Users/wilson/work/presenton
├── servers/fastapi/          # Python backend API
│   ├── api/                  # FastAPI app, routers, middlewares, lifespan
│   ├── services/             # Business logic (chat, export, memory, documents, images)
│   ├── models/               # Pydantic + SQLModel schemas and DB tables
│   ├── utils/                # Env parsing, auth, LLM calls, helpers
│   ├── alembic/              # Database migrations
│   ├── tests/                # pytest tests
│   ├── server.py             # Uvicorn entrypoint
│   ├── mcp_server.py         # MCP server entrypoint
│   └── pyproject.toml        # uv project + pytest config
├── servers/nextjs/           # Next.js 16 App Router frontend
│   ├── app/                  # Routes, route groups, API routes
│   ├── components/           # React components (Radix/shadcn-style UI)
│   ├── store/                # Redux Toolkit slices
│   ├── lib/                  # Internal API clients and helpers
│   ├── tests/                # Node test-runner tests
│   └── package.json
├── electron/                 # Electron desktop app
│   ├── app/                  # Main-process TypeScript source
│   ├── scripts/              # Build/runtime helpers
│   ├── resources/            # Bundled Next.js, FastAPI, export runtime, Chromium
│   ├── build.js              # electron-builder programmatic config
│   └── package.json
├── scripts/                  # Shared root scripts
│   ├── sync-presentation-export.cjs
│   ├── user-config-env.mjs
│   └── presenton-terminal-banner.mjs
├── docs/                     # Provider & build docs
├── .github/workflows/        # CI/CD
├── Dockerfile / Dockerfile.dev
├── docker-compose.yml
├── nginx.conf
└── start.js                  # Container runtime orchestrator
```

### Main code divisions

- **AI generation pipeline** — upload/prompt → SSE outline generation → layout preparation → streamed slide generation.
- **Editor & assets** — drag/reorder slide editor, chat-based editing, image/icon picker, theme/font management, image generation.
- **Templates** — built-in themes under `app/presentation-templates/` plus a Custom Template Studio that compiles uploaded PPTX files into React layouts.
- **Export** — PPTX/PDF generation via the bundled `presenton-export` runtime; MP4 video export via FFmpeg. MP4 exports with speaker-note narration now use dynamic per-slide durations based on the actual TTS audio length plus a short pause between slides, and the export UI lets users pick the Chatterbox voice, output format, speed, and language before exporting.
- **Auth** — single admin account with session cookies + HTTP Basic fallback. Electron disables auth by default.

---

## Runtime architecture

### Docker / web runtime

Inside the container, `start.js` (run via `node /app/start.js`) does the following:

1. Ensures `presentation-export` runtime is present.
2. Optionally installs/starts Ollama if `START_OLLAMA=true`.
3. In dev mode, runs `npm install` inside `servers/nextjs`.
4. Writes `app_data/userConfig.json` from environment variables unless `CAN_CHANGE_KEYS=false`.
5. Starts `nginx`.
6. Spawns:
   - FastAPI on `127.0.0.1:8000` (`python server.py --port 8000 ...`)
   - MCP server on `127.0.0.1:8001` (`python mcp_server.py --port 8001`)
   - Next.js on `127.0.0.1:3000` (standalone `server.js` in production, `npm run dev` in dev)
7. Keeps the Node process alive until one of the servers exits.

`nginx.conf` then exposes everything on port `80`:

- `/` → Next.js `:3000` (WebSocket upgrade headers preserved)
- `/api/v1/` → FastAPI `:8000` (`client_max_body_size 110M`)
- `/docs`, `/openapi.json` → FastAPI
- `/mcp/` and `/mcp` → MCP server `:8001` (auth-gated)
- `/static/` → `servers/fastapi/static/` (public)
- `/app_data/images/` → public
- `/app_data/exports/`, `/app_data/uploads/`, `/app_data/fonts/`, `/app_data/pptx-to-html/` → behind `/_auth_check` subrequest to `/api/v1/auth/verify`

Default external port is `5001` (`PRESENTON_HTTP_HOST_PORT`). Port `1455` is mapped for the Codex OAuth callback.

### Electron runtime

`electron/app/main.ts` starts a local FastAPI server and a local Next.js server, then loads `localhost:<nextjsPort>` in a `BrowserWindow`. The preload script (`electron/app/preloads/index.ts`) exposes `window.env` and `window.electron` APIs via `contextBridge`. Electron sets `PRESENTON_ELECTRON=true` and `DISABLE_AUTH=true` by default, so the MCP server is not started in the desktop build.

---

## Development setup

Prerequisites:

- Node.js 20 + npm
- Python 3.11
- `uv` for Python dependency management
- (Optional) Docker for container builds/tests

### Electron desktop development

```bash
cd electron
npm run setup:env      # installs Node deps, uv syncs FastAPI, installs Next.js deps, prepares export runtime + ImageMagick
npm run dev            # compiles TypeScript and starts Electron with --no-sandbox
```

### Docker development

```bash
# Development with live code mount
docker compose up development

# Production-like
docker compose up production

# Custom host port
PRESENTON_HTTP_HOST_PORT=8080 docker compose up production
```

### Backend-only development

```bash
cd servers/fastapi
uv sync --dev
export APP_DATA_DIRECTORY=/tmp/app_data
export DATABASE_URL=sqlite+aiosqlite:///./dev.db
python server.py --port 8000 --reload true --log-level info
```

### Frontend-only development

```bash
cd servers/nextjs
npm install
npm run dev
```

---

## Build commands

### Root

```bash
npm run sync:presentation-export            # download pinned presentation-export runtime
npm run sync:presentation-export:force      # force re-download
npm run check:presentation-export           # verify runtime is present
```

### Electron

Run these from `electron/`:

```bash
npm run typecheck                # tsc --noEmit
npm run build:ts                 # rm app_dist && tsc
npm run lint:main                # build:ts + check:main-no-undef
npm run build:nextjs             # build Next.js standalone resources into resources/nextjs
npm run build:fastapi            # PyInstaller build of FastAPI into resources/fastapi
npm run build:export-runtime     # sync export runtime
npm run prepare:imagemagick      # bundle ImageMagick
npm run prepare:export-chromium  # bundle Chromium for export
npm run build:electron           # full electron build pipeline (not installer)
npm run build:all                # clean + setup:env + build everything
npm run dist                     # build distributables (dmg/deb/exe/etc.) via electron-builder
```

MAS (Mac App Store) variants exist: `build:electron:mas-dev`, `build:electron:mas`, `build:all:mas-dev`, `build:all:mas`.

### Next.js

Run these from `servers/nextjs/`:

```bash
npm run dev
npm run build
npm run start
npm run lint
npm run test:export-output-path
npm run test:layout-code
npm run check:layout-code
```

Build with the public URLs set:

```bash
NEXT_PUBLIC_FAST_API=http://localhost:8000 NEXT_PUBLIC_URL=http://localhost:3000 npm run build
```

### FastAPI

```bash
cd servers/fastapi
uv sync --dev
python server.py --port 8000 --reload false --log-level warning
python mcp_server.py --port 8001
```

PyInstaller build:

```bash
cd servers/fastapi
uv run --with pyinstaller python -m PyInstaller --distpath ../../electron/resources server.spec
```

### Docker production image

```bash
docker build -t presenton:test -f Dockerfile .
```

---

## Testing instructions

### FastAPI (pytest)

```bash
cd servers/fastapi
uv sync --dev
export APP_DATA_DIRECTORY=/tmp/app_data
export TEMP_DIRECTORY=/tmp/presenton
export DATABASE_URL=sqlite+aiosqlite:///./test.db
export DISABLE_ANONYMOUS_TRACKING=true
export DISABLE_IMAGE_GENERATION=true
export PYTHONPATH=$(pwd)
pytest tests/ -v --tb=short
```

Coverage is configured in `pyproject.toml` with `pytest-cov`. Branch coverage is disabled by default (`branch = false`).

### Next.js

```bash
cd servers/nextjs
npm run check:layout-code
npm run test:layout-code
npm run test:export-output-path
npm run lint
NEXT_PUBLIC_FAST_API=http://localhost:8000 NEXT_PUBLIC_URL=http://localhost:3000 npm run build
```

Cypress component tests are configured but optional:

```bash
npx cypress run --component
```

### Local all-in-one

```bash
./test-local.sh
```

This runs FastAPI pytest, Next.js lint + build, and a Docker build if Docker is available.

### CI

`.github/workflows/test-all.yml` runs on push/PR to `main`:

- `test-fastapi` job — installs deps, sets env vars, builds the PyInstaller binary. **Note: it does not currently run pytest.**
- `test-nextjs` job — `npm ci`, `check:layout-code`, `test:layout-code`, `npm run build`, optional Cypress.

`.github/workflows/docker-release.yml` builds and pushes a multi-arch (`linux/amd64`, `linux/arm64`) image to `ghcr.io/presenton/presenton` on release.

`.github/workflows/sync-releaes-to-r2.yml` uploads desktop release assets (`.deb`, `.dmg`, `.exe`) to Cloudflare R2.

---

## Code style guidelines

### TypeScript / Next.js

- ESM everywhere (`"type": "module"` in relevant `package.json` files).
- Strict TypeScript (`strict: true`).
- Path alias `@/*` maps to the source root.
- UI built with Tailwind CSS 3 + Radix UI primitives in `components/ui/`.
- ESLint config is `servers/nextjs/eslint.config.mjs`; it extends Next.js core-web-vitals + TypeScript configs but intentionally disables many rules to preserve the existing baseline.
- Component files use PascalCase; route files follow Next.js App Router conventions; grouped routes use `(group)/` syntax.

### Python / FastAPI

- Python 3.11 required (`>=3.11,<3.12`).
- Use `uv` for dependency management; lockfile is `uv.lock`.
- Modules use `snake_case`.
- Routers are uppercase constants (e.g., `API_V1_PPT_ROUTER`).
- Async SQLModel/SQLAlchemy is used for database access.
- Alembic migrations live in `alembic/versions/`.
- No explicit Ruff/Black config is present in `pyproject.toml` beyond pytest/coverage.

### Electron

- Main-process source is in `electron/app/`.
- TypeScript compiles to CommonJS in `electron/app_dist/`.
- Preload uses `contextBridge` to expose a minimal API surface.
- Build helpers live in `electron/scripts/`.

### General conventions

- Keep changes minimal and focused.
- `CONTRIBUTING.md` currently restricts accepted code contributions to `electron/`.
- Branch names: `feature/...`, `fix/...`, `docs/...`.

---

## Deployment processes

### Docker / container

```bash
# Single container
docker run -it --name presenton -p 5001:80 -v "./app_data:/app_data" ghcr.io/presenton/presenton:latest

# Compose
PRESENTON_HTTP_HOST_PORT=8080 docker compose up production
```

Compose services: `production`, `production-gpu`, `development`, `development-gpu`. GPU services reserve NVIDIA GPUs via `deploy.resources.reservations.devices`.

### DigitalOcean App Platform

`.do/deploy.template.yaml` defines a one-click deploy using `ghcr.io/presenton/presenton:latest` on port `80` with `MIGRATE_DATABASE_ON_STARTUP=true` and `START_OLLAMA=false`.

### Desktop releases

Electron packages are produced by `electron/build.js` + `electron-builder`. Release assets (`.deb`, `.dmg`, `.exe`) are uploaded to Cloudflare R2 (`presenton-desktop/<version>`) by the `sync-releaes-to-r2.yml` workflow.

---

## Security considerations

- **Single admin account** per instance. Credentials are stored hashed (PBKDF2-SHA256, 200,000 iterations) in `app_data/userConfig.json`.
- **Session tokens** are HMAC-signed JSON payloads with a 30-day TTL. The signing secret is also stored in `userConfig.json`.
- **API keys** entered through the UI are written to `userConfig.json` (plain JSON, not encrypted at rest). Set `CAN_CHANGE_KEYS=false` to prevent UI/env modification of keys.
- **Env-based credential preseed** can be done with `AUTH_USERNAME` + `AUTH_PASSWORD`. Use `AUTH_OVERRIDE_FROM_ENV=true` to rotate credentials (invalidates existing sessions). Use `RESET_AUTH=true` for a one-time reset.
- **Authentication middleware** (`SessionAuthMiddleware`) protects `/api/v1/*`, `/app_data/*` (except images), `/docs`, `/openapi.json`, and `/redoc`. `/api/v1/auth/` routes are exempt. Electron disables this entirely (`DISABLE_AUTH=true`).
- **nginx static access** for user data paths (`exports`, `uploads`, `fonts`, `pptx-to-html`) is gated by an `auth_request` subrequest to `/api/v1/auth/verify`. `/static/` and `/app_data/images/` are public.
- **MCP endpoint** (`/mcp`) requires authentication when auth is configured; it is disabled in the Electron app.
- **Secrets in CI** — GitHub Actions use `GITHUB_TOKEN`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_ACCOUNT_ID`.
- **Electron sandbox** — Linux builds disable Chromium sandbox when the `chrome-sandbox` binary does not have the expected setuid/root ownership.

---

## Useful pointers

- Environment variable parsing: `servers/fastapi/utils/get_env.py`
- User-config mapping from env: `scripts/user-config-env.mjs`
- Auth implementation: `servers/fastapi/utils/simple_auth.py`
- FastAPI app entry: `servers/fastapi/api/main.py`
- Next.js config: `servers/nextjs/next.config.mjs`
- Electron build config: `electron/build.js`
- Runtime orchestrator: `start.js`
- Export runtime sync: `scripts/sync-presentation-export.cjs` and `electron/scripts/sync-export-runtime.cjs`

### Known quirks

- The root `package.json` version is `0.8.7` while `electron/package.json` is `0.8.8-beta`.
- The pinned presentation-export runtime version is `v0.3.6` (`presentationExportVersion`).
- The CI `test-fastapi` job builds the PyInstaller binary but does not run `pytest`; `test-local.sh` does.
