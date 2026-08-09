#!/usr/bin/env python3
"""Benchmark worker — prompt via stdin, result via stdout."""
import os, sys, json

os.environ['AXIO_CPA_PLUS_BASE_URL'] = 'http://127.0.0.1:8317/v1'
os.environ['AXIO_CPA_PLUS_API_KEY'] = 'sk-S9APc6QARCPCC4AeM'
os.environ['no_proxy'] = '127.0.0.1,localhost'

sys.path.insert(0, '/home/he/axio_fusion_api/src')

REG_PATH = '/home/he/axio_fusion_api/private/runs/2026-08-09-prefusion-cohort-r43/runtime_registry.probe-bound.r43.private.json'
CPA_URL = 'http://127.0.0.1:8317/v1/responses'
CPA_KEY = 'sk-S9APc6QARCPCC4AeM'
MAX_TOKENS = 512

def run_axio(model, prompt):
    from axio_fusion_api.registry import load_registry
    from axio_fusion_api.providers import HTTPProviderClient
    from axio_fusion_api.orchestrator import FusionEngine
    from axio_fusion_api.schemas import FusionRequest
    profiles = load_registry(REG_PATH, require_prefusion=False)
    client = HTTPProviderClient(require_streaming=True)
    engine = FusionEngine(profiles, client=client)
    req = FusionRequest(model=model, prompt=prompt, max_output_tokens=MAX_TOKENS)
    resp = engine.complete(req)
    text = resp.text if resp and resp.text else ''
    sys.stdout.write(text)
    sys.stdout.flush()

def run_cpa(model, prompt):
    import requests
    body = {'model': model, 'input': prompt, 'max_output_tokens': MAX_TOKENS, 'reasoning': {'effort': 'max'}}
    h = {'Content-Type': 'application/json', 'Authorization': f'Bearer {CPA_KEY}'}
    r = requests.post(CPA_URL, json=body, headers=h, timeout=90)
    if r.status_code == 200:
        data = r.json()
        for item in data.get('output', []):
            if item.get('type') == 'message':
                for c in item.get('content', []):
                    if c.get('type') == 'output_text':
                        sys.stdout.write(c['text'])
                        sys.stdout.flush()
                        return
        sys.stdout.write(json.dumps(data)[:500])
    else:
        sys.stdout.write(f'HTTP{r.status_code}')
    sys.stdout.flush()

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['axio', 'cpa'], required=True)
    ap.add_argument('--model', required=True)
    args = ap.parse_args()
    prompt = sys.stdin.read()
    if args.mode == 'axio':
        run_axio(args.model, prompt)
    else:
        run_cpa(args.model, prompt)
