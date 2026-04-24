#!/bin/bash
set -e

echo "[*] Setting up Red Team environment..."
pip install garak agentic_security
export PYTHONPATH=src

echo "[*] Starting Red Team Bridge (Adapter) on port 11435 in background..."
python tests/redteam_adapter.py &
ADAPTER_PID=$!

echo "[*] Waiting a few seconds for server to start..."
sleep 3

echo "[*] Launching Garak Red Team tests against AgentLoop..."
# You can customize probes. e.g. promptinject, lmrc, attck
python -m garak --model_type openai --model_name biopipe --rest_endpoint http://127.0.0.1:11435/v1/chat/completions --probes promptinject --request_timeout 60

echo "[*] Garak finished. Stopping adapter."
kill $ADAPTER_PID
