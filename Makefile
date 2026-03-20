# Foreign Whispers — Docker Compose helpers
PROFILE := --profile nvidia
DC      := docker compose $(PROFILE)
API     := api-gpu
NB      := notebooks/foreign_whispers_pipeline.ipynb

# ── Docker lifecycle ──────────────────────────────────────────────────────
.PHONY: build up down logs ps

build:                ## Rebuild the API image
	$(DC) build $(API)

up:                   ## Start all services
	$(DC) up -d

down:                 ## Stop all services
	$(DC) down

logs:                 ## Tail logs for all services
	$(DC) logs -f

ps:                   ## Show running containers
	$(DC) ps

rebuild: build up     ## Rebuild API and restart

# ── Notebook execution ────────────────────────────────────────────────────
.PHONY: notebook-deps notebook notebook-skip-heavy

notebook-deps:        ## Install notebook runtime deps in the API container
	$(DC) exec $(API) uv pip install nbclient ipykernel
	$(DC) exec $(API) uv run python3 -m ipykernel install --user --name python3

notebook: notebook-deps  ## Run the full notebook inside the API container
	$(DC) exec -w /app/notebooks $(API) uv run python3 -c " \
		from nbclient import NotebookClient; \
		import nbformat; \
		nb = nbformat.read('foreign_whispers_pipeline.ipynb', as_version=4); \
		client = NotebookClient(nb, timeout=1200, kernel_name='python3'); \
		client.execute(); \
		nbformat.write(nb, 'foreign_whispers_pipeline_executed.ipynb'); \
		print('Notebook executed successfully.'); \
	"

notebook-quick: notebook-deps  ## Run notebook, skipping subtitle burn-in and batch cells
	$(DC) exec -w /app/notebooks $(API) uv run python3 -c " \
		from nbclient import NotebookClient; \
		import nbformat; \
		nb = nbformat.read('foreign_whispers_pipeline.ipynb', as_version=4); \
		heavy = [44, 48]; \
		for idx in heavy: \
			cell = nb['cells'][idx]; \
			if cell['cell_type'] == 'code': \
				cell['source'] = 'print(\"Skipped (heavy cell)\")'; \
		client = NotebookClient(nb, timeout=600, kernel_name='python3'); \
		client.execute(); \
		nbformat.write(nb, 'foreign_whispers_pipeline_executed.ipynb'); \
		print('Notebook executed successfully (quick mode).'); \
	"

notebook-check: notebook-deps  ## Run notebook with allow_errors and report pass/fail per cell
	$(DC) exec -w /app/notebooks $(API) uv run python3 -c " \
		from nbclient import NotebookClient; \
		import nbformat; \
		nb = nbformat.read('foreign_whispers_pipeline.ipynb', as_version=4); \
		client = NotebookClient(nb, timeout=600, kernel_name='python3', allow_errors=True); \
		client.execute(); \
		ok = fail = 0; \
		for i, cell in enumerate(nb['cells']): \
			if cell['cell_type'] != 'code': continue; \
			errors = [o for o in cell.get('outputs', []) if o.get('output_type') == 'error']; \
			src = ''.join(cell['source']).split(chr(10))[0][:70]; \
			if errors: \
				fail += 1; \
				ename = errors[0].get('ename', '?'); \
				evalue = errors[0].get('evalue', '?')[:100]; \
				print(f'FAIL cell {i}: {src}'); \
				print(f'  {ename}: {evalue}'); \
			else: \
				ok += 1; \
				print(f'OK   cell {i}: {src}'); \
		print(f'\n{ok} passed, {fail} failed'); \
		exit(1 if fail else 0); \
	"

.PHONY: help
help:                 ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
