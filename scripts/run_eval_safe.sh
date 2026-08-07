#!/bin/bash
cd /home/he/axio_fusion_api
exec 2>/tmp/eval_safe_err.log
set -x
.venv/bin/python -u scripts/run_eval_now.py
