#!/usr/bin/env python3
"""Benchmark worker — prompt via stdin, result via stdout. Uses HTTP API."""
import os, sys, json, urllib.request, urllib.error

AXIO_URL = 'http://127.0.0.1:18900/v1/chat/completions'
CPA_URL = "http://127.0.0.1:8317/v1/responses"
CPA_KEY = 'sk-S9APc6QARCPCC4AeM'
MAX_TOKENS = 512
TIMEOUT = 90

def run_axio(model, prompt):
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': MAX_TOKENS,
        'stream': False
    }).encode()
    req = urllib.request.Request(AXIO_URL, data=body,
        headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        data = json.loads(resp.read())
        text = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        sys.stdout.write(text or json.dumps(data)[:500])
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')[:300]
        sys.stdout.write(f'HTTP{e.code}:{body}')
    except Exception as e:
        sys.stdout.write(f'ERR:{type(e).__name__}:{str(e)[:200]}')
    sys.stdout.flush()

def run_cpa(model, prompt):
    body = json.dumps({
        'model': model,
        'input': prompt,
        'max_output_tokens': MAX_TOKENS,
        'reasoning': {'effort': 'max'}
    }).encode()
    req = urllib.request.Request(CPA_URL, data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {CPA_KEY}'})
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        data = json.loads(resp.read())
        for item in data.get('output', []):
            if item.get('type') == 'message':
                for c in item.get('content', []):
                    if c.get('type') == 'output_text':
                        sys.stdout.write(c['text'])
                        sys.stdout.flush()
                        return
        sys.stdout.write(json.dumps(data)[:500])
    except urllib.error.HTTPError as e:
        sys.stdout.write(f'HTTP{e.code}')
    except Exception as e:
        sys.stdout.write(f'ERR:{type(e).__name__}:{str(e)[:200]}')
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
