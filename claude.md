# Doane IT — Working Context for Claude Code

> Global context for Todd Finner's Claude Code sessions. This file lives at
> `~/.claude/CLAUDE.md` and loads automatically. Project-specific overrides
> belong in a `CLAUDE.md` at the project root.

---

## 1. Who I am

Todd Finner, senior IT developer at Doane University (Crete, Nebraska).
16+ years experience.

**Core stack:** Python, C# (.NET), Java, SQL Server, PowerShell. Heavy work with
Ellucian Colleague ERP, Ethos APIs, Orkes Conductor, Kubernetes/Traefik,
Databricks, Salesforce Education Cloud, n8n.  I can be flexible on the front end
if we find a need beyond Python and c#.  Most of our conductor services run in
C# and some of our one-off projects are in python.  If there are questions
before beginning a project, please ask.

**Doane context:** small private liberal arts university (~2,000 students:
undergrad, grad, adult learners). IT is small, so projects often need to be
built and maintained by 1-2 people. The Doane Automation Initiative is
identifying 100+ workflow automation opportunities across 14 institutional
areas (admissions, advancement, registrar, student affairs, etc.).
"Stakeholder" usually means a department head or director, not an external
vendor. Production systems are mission-critical even at small scale.

---

## 2. Operating principles

### Working approach
- Open to direct criticism and pushback. Don't soften feedback unnecessarily.
- Full commitment from the start — no shortcuts, no surface-level treatment.
  Trust that whatever is put together that it can be read, debugged, etc. by
  the engineering team.  Don't be afraid to think outside the box if needed.
- Code style: simple, well-commented with functional notes only.
- Comments explain WHY or note non-obvious context. "# loop through items"
  gets removed.
- Minimal preamble. Get to the substance.

### When to ask vs assume

**Ask when the answer materially changes what gets built:**
- Choice of database (SQL Server vs Postgres vs SQLite)
- Choice of auth pattern (none, basic, OAuth, SSO)
- Whether a service is internal-only or publicly exposed
- Integration points (which Ethos endpoints, which SF objects)
- Whether tests are in scope

**Don't ask for things the standard already answers:**
- File structure (use the project output standard)
- Logging format (JSON to stdout)
- Health endpoint shape (already defined)
- Launcher script (use the template)

**Default behavior on ambiguity:** ask once, get answer, proceed.

### Anti-patterns — don't do these without asking
- Don't add new dependencies without flagging them. If a task seems to need a
  new library, propose it before adding to requirements.txt.
- Don't introduce new frameworks (FastAPI when Flask is the standard, Poetry
  when pip+requirements is the standard, pytest fixtures when none exist yet).
- Don't refactor adjacent code while making a focused change. Touch only what
  the task requires.
- Don't generate placeholder/example values that look real (fake API keys,
  fake emails). Use obvious placeholders like `REPLACE_ME` or `<your-key-here>`.
- Don't auto-format the whole file when making a small edit. Match existing
  style even if it's inconsistent.
- Don't write README.md unless explicitly asked. The Doane standard is
  `docs/bashCommands.txt` for project-specific commands.

---

## 3. Project standards

### Project output structure

Every project should be ready to copy-paste into `C:\doane\code\`.

**Required files (always create):**
- `start-local.ps1` in project root (Doane launcher standard)
- `.gitignore` including `.venv/`, `.env`, `.hub-logs/`, `node_modules/`
- `.env.example` listing required env vars (with `REPLACE_ME` placeholders)
- `requirements.txt` (always include `python-dotenv` for Flask)
- `docs/bashCommands.txt` — project-specific useful commands (cd to project,
  venv activation, common debug/test commands; minimum is enough to get
  someone re-oriented six months later)
- `.pyproj` or `.sln` (Visual Studio full IDE — NOT VS Code)
- All source files in correct folders

**Files NOT to create unless asked:**
- README.md, CONTRIBUTING.md, LICENSE, CHANGELOG.md
- `.github/` workflows
- `.editorconfig`, `.pre-commit-config.yaml`
- Test scaffolding unless tests are part of the request
- Dockerfile unless K8s deployment is part of the request

If unsure whether to create a file, ask first.

### Naming conventions
- Project directory names: **kebab-case** (`dep-graph-service`, not
  `DepGraphService` or `dep_graph_service`)
- Project names in projects.json: **Title Case** ("Dep Graph Service")
- Service names in K8s manifests: kebab-case matching directory
- Docker image: `doaneu/<kebab-case-name>:latest`
- Python modules within: `snake_case`
- Database identifiers: `snake_case`

**Project paths:**
- `C:\doane\code\<kebab-case-name>` for shared services
- `C:\doane\Personal\<kebab-case-name>` for solo/exploratory work

### Canonical templates

When scaffolding a new project, base it on one of these patterns:
- **Flask service** → mirror `dlm-service` or `dep-graph-service`
- **Flask + Vite** → mirror `dep-graph-service`
- **Conductor worker** → mirror existing Python custom worker pattern
- **n8n workflow** → JSON export, no scaffolding needed
- **Static site** → minimal `start-local.ps1` wrapping `npx serve`
- **Docker Compose service** → mirror `n8n-local` shape

If a new project doesn't fit one of these, ask before inventing a new pattern.

### Bulk generation context

This is a parent directory for 100+ projects identified in the Doane Automation
Initiative. Scaffolding will happen in waves. Each project should:
- Be independently runnable with zero-arg `start-local.ps1`
- Have a populated `docs/bashCommands.txt` with at minimum: cd to project,
  activate venv, run `start-local.ps1`
- Have a `.env.example` with placeholder values, even if `.env` contents are
  trivial
- NOT depend on adjacent projects for compilation or first-run

If a project genuinely needs another to be running (e.g., a Conductor worker
needs Conductor up), document it in `docs/bashCommands.txt` under a
"Prerequisites" section.

---

## 4. Launcher standard (start-local.ps1)

Every project has `start-local.ps1` in the root as the hub-service launch
target.

### Contract
- Zero-arg invocation must start the project in default dev configuration.
- `start_command` in projects.json: `powershell -File start-local.ps1`
  (NO `.\` — shlex POSIX mode eats the backslash; hub auto-resolves bare
  `.ps1` paths against `project_path`).
- Direct terminal use DOES need `.\` (shell doesn't auto-resolve).
- Templates exist for flask-only and flask-vite variants.

### Critical PS1 details
- `python -u` flag when redirecting stdout to file (else tracebacks lost to
  buffer).
- Wipe BOTH `$Log` and `$Log.err` per run.
- Set `FLASK_DEBUG` once via inline `if/else` (don't duplicate the assignment).
- Filter `127.x.x.x`, `169.254.x.x` (APIPA), and `vEthernet`/`WSL` from LAN IP
  enumeration.
- Always plain ASCII in `.ps1` (no Unicode box-drawing, em dashes; use `---`
  for dividers).

### Hub-service Popen requirements

For code that launches Flask children via subprocess:

- **MUST filter** `WERKZEUG_RUN_MAIN` and `WERKZEUG_SERVER_FD` from child env.
  When hub itself runs under `flask run`, the reloader sets these on its own
  process, Popen inherits them, and children die with
  `OSError: [WinError 10038] An operation was attempted on something that is
  not a socket`.
- **Never** `shell=True` or `CREATE_NEW_CONSOLE` (cmd.exe `/c` flash-dies in
  ~50ms).
- Use `CREATE_NEW_PROCESS_GROUP`, redirect to
  `<project>/.hub-logs/launch-<ts>.log`.
- Flask apps use `app.run(use_reloader=False)` to prevent reloader fork
  env leak.

### Stale venv pattern

Updating `requirements.txt` does NOT auto-reinstall. Venv stays stale until
either `-ForceDeps` flag to `start-local.ps1` OR manual
`pip install -r requirements.txt` in the activated venv. If
`ModuleNotFoundError` hits after a recent `requirements.txt` change, first
suggestion is always `-ForceDeps`.

---

## 5. Service standards (apply to every new project)

1. **Logs:** Structured JSON to stdout with `timestamp`, `level`, `service`,
   `request_id`, `message` via Python logging module.
2. **Health:** GET `/health` returns
   `{status: "ok", service: name, version: "x.x.x", uptime_seconds: N}`.
   Used by K8s probes and hub port checks.
3. **API:** Error shape `{error: msg, code: CODE, request_id: ...}`. Version
   under `/api/v1/` from day one.
4. **Configurability:** provider, model, institution via `.env`
   (`STAKEHOLDER=doane`, `AI_PROVIDER=anthropic`, `AI_MODEL=...`).

### Hub run_type field

Classification dimension on projects in `projects.json`. Drives display badge
plus future dispatch logic. Standard values:
`flask`, `flask-vite`, `python`, `dotnet`, `node`, `docker-compose`,
`conductor`, `n8n-workflow`, `static`, `meta`.

---

## 6. Technical defaults

### Version defaults (when nothing else is specified)
- Python: **3.11**
- Node: **20 LTS**
- .NET: **8**
- Flask: **3.x**
- SQLAlchemy: **2.x**
- React: **18**
- Vite: **5**
- n8n: pin to current version in `n8n-local` docker-compose, don't use `:latest`
- Postgres: **16**
- SQL Server: **2022**

When generating `requirements.txt`, prefer `package>=X.Y.Z,<X+1.0.0` to allow
patch updates without major-version surprise.

### Stack preferences
- Default production backend: **SQL Server** (unless service specifically
  targets Postgres or SQLite).
- **Databricks Unity Catalog Files API** uses OAuth with service principal
  (NOT PAT); volume path `/Volumes/bronze/ethos/files`; DateTime format
  `yyyy-MM-dd HH:mm:ss.fff`.
- **Ethos integrations** use custom HttpClient with explicit
  `Accept: application/json` + Bearer token (NO third-party graphql-client
  packages).
- **DLM Service URL:** `https://du-int.doane.edu/dlm`.

### Python/Windows specifics
- venv setup: always "Add Environment → Existing environment" pointing to
  `.venv\Scripts\python.exe` (NOT "Virtual environment" which creates a new
  one).
- Flask launch env vars in Project Properties > Debug.
- pyodbc needs ODBC Driver 17 system-wide.
- PaddleOCR on Windows: set `$env:FLAGS_use_mkldnn = '0'` before
  `flask run` in `start-local.ps1` (Linux K8s production unaffected).

### Doane brand
- Orange `#FF7900`
- Dark Navy `#1F3864`
- White `#FFFFFF`
- Black `#000000`

---

## 7. Domain conventions

### Conductor workflow pattern
- SIMPLE tasks with custom workers (`ethos_get_by_id`, `ethos_get_by_filter`,
  `upsert_salesforce_hed_record`) — NOT HTTP tasks.
- Inputs from Ethos change notifications:
  `workflow.input.resource.id`, `.content.id`, `.operation`.
- SF upserts use external ID (`SIS_ID__c`) with nested relationship attributes.
- Workers handle auth.
- SWITCH on operation via value-param.
- `JSON_JQ_TRANSFORM` (NOT `INLINE` or `GraalJS`) for data extraction /
  string building.
- `ethos_guid__c` on SF objects replaces d45 keymaps (fully retired).

### Conductor HTTP URLs
- **Local dev:** `host.docker.internal:PORT` when Conductor runs in Docker
  Compose calling Flask on Windows host (`localhost` in container = container
  itself).
- **Production:** `https://du-int.doane.edu/prod/service-name`.
- Always swap when moving between environments.

### Salesforce Ed Cloud Person Account pattern
- Person data upserts go to **Account** (NOT Contact) using `__pc` suffix
  fields (e.g. `Legal_First_Name__pc`). SF auto-creates the Contact.
- ContactPoint records (email, phone, address) parent to Account/Individual.
  ParentId domain is Master-Detail(Individual, Account).
- `SIS_ID__c` and `Ethos_Guid__c` on both Account and Contact.
- Nested relationship refs for ContactPoints use Account type.

### K8s deployment pattern
- Namespace: `prod`
- Host: `du-int.doane.edu`
- TLS secret: `wildcard-doane-tls`
- Cert issuer: `prod-letsencrypt`
- imagePullSecrets: `regcred`
- Path: `/prod/service-name` with Traefik stripPrefix middleware
- Middleware naming: `prod-{service-name}-prefix@kubernetescrd`
- Flask sees clean paths — no route adjustments needed for K8s prefix.
- Double-check secretKeyRef indentation in generated manifests
  (known error-prone).
- Docker images pushed to `doaneu/` org on Docker Hub.

---

## 8. Active context

### What I'm currently working on
- **Salesforce EDA → Education Cloud migration** (active, multi-session)
- **Hub-service:** project launcher for local dev with HTTP health checks
- **n8n local instance** with vectorized doane.edu RAG (Thomas the Tiger)
- **Dep-graph-service:** institutional dependency mapping with cascade
  simulation
- **Doane Automation Initiative:** scaffolding ~100+ projects across 14
  institutional areas — this is the parent context for most bulk-generation
  work
- Various retrofits to bring older projects (OCR, esports, DLM) onto current
  standards
