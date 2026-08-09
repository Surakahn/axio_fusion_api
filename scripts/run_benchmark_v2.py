#!/usr/bin/env python3
"""Robust benchmark runner with proper timeouts and direct CPA access."""
import os, sys, json, time, signal, random
from pathlib import Path
from collections import defaultdict

# ── Config ──────────────────────────────────────────────
os.environ.setdefault('AXIO_CPA_PLUS_BASE_URL', 'http://127.0.0.1:8317/v1')
os.environ.setdefault('AXIO_CPA_PLUS_API_KEY', 'sk-S9APc6QARCPCC4AeM')
os.environ.setdefault('no_proxy', '127.0.0.1,localhost')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from axio_fusion_api.registry import load_registry
from axio_fusion_api.providers import HTTPProviderClient
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.schemas import FusionRequest
import requests

REG_PATH = '/home/he/axio_fusion_api/private/runs/2026-08-09-prefusion-cohort-r43/runtime_registry.probe-bound.r43.private.json'
BENCH_DIR = Path('/mnt/storage/axio_fusion_benchmarks/standardized')
OUTPUT = Path('/home/he/axio_fusion_api/private/bench_results_v2.json')
CPA_URL = 'http://127.0.0.1:8317/v1/responses'
CPA_KEY = 'sk-S9APc6QARCPCC4AeM'
SAMPLES = 5
MAX_TOKENS = 300
TIMEOUT_SEC = 90

AXIO_MODELS = ['axio-fast', 'axio-terra', 'axio-pro']
BASELINE_MODELS = ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6-sol']

SUITES = {
    'arc_challenge':         {'cat':'logic','fmt':'mcq','qk':'question','ok':'options','ak':'answer'},
    'bbh':                   {'cat':'logic','fmt':'open','qk':'prompt','ak':'answer'},
    'math_500':              {'cat':'math','fmt':'math','qk':'prompt','ak':'answer'},
    'aime_recent':           {'cat':'math','fmt':'math','qk':'prompt','ak':'answer'},
    'global_mmlu_lite':      {'cat':'multilingual','fmt':'mcq','qk':'question','ok':'options','ak':'answer'},
    'truthfulqa':            {'cat':'hallucination','fmt':'mcq','qk':'question','ok':'options','ak':'answer'},
    'mmmu_text_science':     {'cat':'science','fmt':'mcq','qk':'question','ok':'options','ak':'answer'},
    'medqa_usmle':           {'cat':'vertical','fmt':'mcq','qk':'question','ok':'options','ak':'answer'},
    'legalbench':            {'cat':'vertical','fmt':'mcq','qk':'question','ok':'options','ak':'answer'},
    'bizbench':              {'cat':'vertical','fmt':'open','qk':'prompt','ak':'answer'},
    'policyllm_policybench': {'cat':'vertical','fmt':'mcq','qk':'question','ok':'options','ak':'answer'},
}

# ── Pipeline ────────────────────────────────────────────
engine = None
_client = None

def get_engine():
    global engine, _client
    if engine is None:
        profiles = load_registry(REG_PATH, require_prefusion=False)
        _client = HTTPProviderClient(require_streaming=True)
        engine = FusionEngine(profiles, client=_client)
    return engine

def load_suite(name):
    path = BENCH_DIR / f'{name}.jsonl'
    if not path.exists(): return []
    return [json.loads(l) for l in open(path) if l.strip()]

def build_prompt(case, meta):
    fmt = meta['fmt']
    q = str(case.get(meta['qk'], ''))
    if fmt == 'mcq':
        opts = case.get(meta.get('ok','options'), {})
        if isinstance(opts, str):
            try: opts = eval(opts)
            except: opts = {}
        opt_lines = '\n'.join(f'{k}: {v}' for k,v in sorted(opts.items()))
        return f'{q}\n\nOptions:\n{opt_lines}\n\nAnswer with just the option letter (A/B/C/D).'
    return q

def score(pred, gold, fmt):
    p = str(pred).strip()
    g = str(gold).strip()
    if fmt == 'mcq':
        return 1.0 if p[:1].upper() == g[:1].upper() else 0.0
    elif fmt == 'math':
        pn = p.replace(',','').strip('$')
        gn = g.replace(',','').strip('$')
        if pn.lower() == gn.lower(): return 1.0
        try: return 1.0 if abs(float(pn)-float(gn)) < 1e-4 else 0.0
        except: return 1.0 if pn == gn else 0.0
    return 1.0 if p.lower() == g.lower() else 0.0

def call_axio(model, prompt):
    eng = get_engine()
    req = FusionRequest(model=model, prompt=prompt, max_output_tokens=MAX_TOKENS)
    signal.alarm(TIMEOUT_SEC)
    try:
        resp = eng.complete(req)
        signal.alarm(0)
        return resp.text if resp and resp.text else '', None
    except Exception as e:
        signal.alarm(0)
        return '', f'{type(e).__name__}: {str(e)[:150]}'

def call_cpa(model, prompt):
    body = {'model':model,'input':prompt,'max_output_tokens':MAX_TOKENS,'reasoning':{'effort':'max'}}
    h = {'Content-Type':'application/json','Authorization':f'Bearer {CPA_KEY}'}
    try:
        r = requests.post(CPA_URL, json=body, headers=h, timeout=TIMEOUT_SEC)
        if r.status_code == 200:
            data = r.json()
            for item in data.get('output',[]):
                if item.get('type')=='message':
                    for c in item.get('content',[]):
                        if c.get('type')=='output_text':
                            return c['text'], None
            return str(data)[:200], None
        return '', f'HTTP{r.status_code}'
    except Exception as e:
        return '', f'{type(e).__name__}: {str(e)[:100]}'

def load_results():
    if OUTPUT.exists():
        with open(OUTPUT) as f:
            return json.load(f)
    return {'runs': [], 'meta': {'samples_per_suite': SAMPLES}}

def save_results(results):
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

# ── Main ─────────────────────────────────────────────────
def main():
    results = load_results()
    completed = {(r['suite'], r['model']) for r in results['runs']}
    
    print(f'=== AXIO FUSION BENCHMARK v2 ===')
    print(f'Suites: {len(SUITES)}, Models: {len(AXIO_MODELS)+len(BASELINE_MODELS)}, Samples: {SAMPLES}')
    print(f'Already completed: {len(completed)}')
    
    for suite_name, meta in SUITES.items():
        cases = load_suite(suite_name)
        if not cases:
            print(f'[SKIP] {suite_name}: no data')
            continue
        
        sampled = random.sample(cases, min(SAMPLES, len(cases)))
        
        for model in AXIO_MODELS + BASELINE_MODELS:
            if (suite_name, model) in completed:
                continue
            
            print(f'\n[{suite_name}] {model} ({meta["fmt"]}, {len(sampled)} cases)')
            correct = errors = 0
            t0 = time.time()
            
            for i, case in enumerate(sampled):
                prompt = build_prompt(case, meta)
                gold = str(case.get(meta['ak'], ''))
                
                if model in BASELINE_MODELS:
                    pred, err = call_cpa(model, prompt)
                else:
                    pred, err = call_axio(model, prompt)
                
                if err:
                    errors += 1
                    print(f'  [{i+1}/{len(sampled)}] ERR: {err[:80]}')
                else:
                    s = score(pred, gold, meta['fmt'])
                    correct += s
                    sym = '✓' if s > 0 else '✗'
                    print(f'  [{i+1}/{len(sampled)}] {sym} pred={pred[:40]} gold={gold[:40]}')
                sys.stdout.flush()
            
            acc = correct / len(sampled) if len(sampled) > 0 else 0
            elapsed = time.time() - t0
            print(f'  → Accuracy: {acc:.2%} ({correct}/{len(sampled)}) in {elapsed:.0f}s')
            
            results['runs'].append({
                'suite': suite_name, 'model': model, 'accuracy': acc,
                'correct': correct, 'samples': len(sampled),
                'errors': errors, 'elapsed_s': round(elapsed, 1),
                'time': time.strftime('%Y-%m-%d %H:%M:%S')
            })
            save_results(results)
    
    # Final summary
    print('\n' + '='*60)
    print('FINAL RESULTS')
    ms = defaultdict(lambda: defaultdict(float))
    for r in results['runs']:
        ms[r['model']][r['suite']] = r['accuracy']
    for m in AXIO_MODELS + BASELINE_MODELS:
        s = ms.get(m, {})
        if s:
            avg = sum(s.values())/len(s)
            print(f'{m:20s} avg={avg:.2%} suites={len(s)}')
    save_results(results)

if __name__ == '__main__':
    main()
