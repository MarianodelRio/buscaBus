# Makefile — Buscabus. Fase 1 incluye validar, formatear y revision.
# La fase 5 amplía este Makefile (publicar, systemd, etc.).

.PHONY: validar formatear revision telegram

validar:
	python -m tools.validar

formatear:
	python -m tools.formatear

revision:
	python -m tools.revision

telegram:
	python -m tools.telegram_pruebas
