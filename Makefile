PYTHON ?= python3
PROJECT_CONFIG ?= configs/project.yaml
PIPELINE = PYTHONPATH=. $(PYTHON) scripts/run_full_pipeline.py --config $(PROJECT_CONFIG)

.PHONY: help setup list-stages data assortment simulation inventory evaluation full validate test dry-run clean-logs

help:
	@echo "FAIA project commands"
	@echo "  make setup        Install project runtime dependencies"
	@echo "  make data         Generate, process, validate and register v001 data"
	@echo "  make assortment   Run and validate the assortment stage"
	@echo "  make simulation   Run and validate the simulation stage"
	@echo "  make inventory    Run and validate the inventory allocation stage"
	@echo "  make evaluation   Collect, report and validate evaluation outputs"
	@echo "  make full         Run all configured stages in order"
	@echo "  make validate     Re-run validation/reporting checks for published outputs"
	@echo "  make test         Run module unit tests"
	@echo "  make dry-run      Print the full pipeline commands without executing them"

setup:
	$(PYTHON) -m pip install -e .

list-stages:
	$(PIPELINE) --list-stages

data:
	$(PIPELINE) --stages data

assortment:
	$(PIPELINE) --stages assortment

simulation:
	$(PIPELINE) --stages simulation

inventory:
	$(PIPELINE) --stages inventory

evaluation:
	$(PIPELINE) --stages evaluation

full:
	$(PIPELINE)

validate:
	PYTHONPATH=. $(PYTHON) data/scripts/validate_stage1_data.py --data-version v001
	PYTHONPATH=. $(PYTHON) assortment/scripts/validate_assortment_run.py --manifest assortment/runs/exp_assortment_v001_topk/assortment_manifest.yaml
	PYTHONPATH=. $(PYTHON) simulation/scripts/validate_simulation_run.py --manifest simulation/runs/sim_smoke_v001_no_transfer/simulation_manifest.yaml
	@if [ -f inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml ]; then \
		PYTHONPATH=. $(PYTHON) inventory/scripts/validate_inventory_run.py --manifest inventory/runs/exp_inventory_v001_base_stock/inventory_manifest.yaml; \
	else \
		echo "skip inventory validation: inventory manifest is not present"; \
	fi
	PYTHONPATH=. $(PYTHON) evaluation/scripts/build_report.py --manifest evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml
	PYTHONPATH=. $(PYTHON) evaluation/scripts/validate_evaluation_run.py --manifest evaluation/runs/eval_v001_baseline/evaluation_manifest.yaml

test:
	PYTHONPATH=. $(PYTHON) -m unittest discover -s simulation/tests
	PYTHONPATH=. $(PYTHON) -m unittest discover -s assortment/tests
	PYTHONPATH=. $(PYTHON) -m unittest discover -s inventory/tests
	PYTHONPATH=. $(PYTHON) -m unittest discover -s evaluation/tests
	PYTHONPATH=. $(PYTHON) -m unittest discover -s tests/integration

dry-run:
	$(PIPELINE) --dry-run

clean-logs:
	rm -rf artifacts/run_logs
