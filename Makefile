.PHONY: help deploy deploy-fast verify test-roadmap install distill doctor production-audit

help:
	@echo "DietCode plugin — common targets"
	@echo ""
	@echo "  make deploy       Sync to ~/.hermes, reinstall Hermes, enable, verify"
	@echo "  make deploy-fast  Sync + verify only (skip Hermes pip reinstall)"
	@echo "  make verify       Doctor, hardening audit, roadmap smoke, and unit tests"
	@echo "  make doctor       Runtime contract + hook registry validation (JSON)"
	@echo "  make production-audit  Scan plugin sources for non-production antipatterns"
	@echo "  make distill      Sync broccolidb core from codemarie-new (CODEMARIE_SRC)"
	@echo "  make install      Run install.py wizard in this checkout"
	@echo ""
	@echo "Env: HERMES_SRC, HERMES_VENV, HERMES_HOME, DIETCODE_PLUGIN_SRC"

deploy:
	./scripts/hermes_deploy.sh

deploy-fast:
	./scripts/hermes_deploy.sh --skip-hermes-reinstall

distill:
	./scripts/distill_from_codemarie.sh
	cd broccolidb && npm test 2>/dev/null | tail -5 || true

verify test-roadmap:
	python3 scripts/dietcode_doctor.py
	python3 scripts/production_hardening_audit.py
	python3 scripts/roadmap_smoke.py
	python3 scripts/roadmap_audit.py
	python3 scripts/roadmap_operator_smoke.py
	python3 -m unittest tests.test_roadmap_checkpoint tests.test_roadmap_tools tests.test_roadmap_external_watch tests.test_project_map_tools tests.test_layer_align tests.test_native_mutation tests.test_mem_tools tests.test_quality_gate tests.test_kanban_complete_gates tests.test_runtime_features tests.test_production_audit -q

production-audit:
	python3 scripts/production_hardening_audit.py

doctor:
	python3 scripts/dietcode_doctor.py

install:
	python3 install.py
