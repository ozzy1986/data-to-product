#!/usr/bin/env bash
# На сервере, от d2p, в папке нового релиза (вызывает deploy.sh): свой venv на релиз → откат симлинком
# возвращает и код, и зависимости. Базы у сервиса нет.
set -euo pipefail
export PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
python3 -m venv venv
venv/bin/pip install -q -r requirements.txt
venv/bin/python -m compileall -q app
