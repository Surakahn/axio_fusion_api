#!/usr/bin/env python3
"""Axio Fusion Benchmark v4 — concurrent HTTP, parallel model calls, 14 suites."""
import os, sys, json, time, random, re
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, TimeoutError, FIRST_COMPLETED
import urllib.request, urllib.error

BENCH_DIR = Path('/mnt/storage/axio_fusion_benchmarks/standardized')
OUTPUT = Path('/home/he/axio_fusion_api/private/bench_results_v4.json')
SAMPLES = 8
TIMEOUT_SEC = 60
MAX_WORKERS = 6  # Parallel HTTP calls

AXIO_URL = 'http://127.0.0.1:18900/v1/chat/completions'
CPA_URL = 'http://127.0.0.1:8317/v1/responses'
CPA_KEY = 'sk-S9APc6QARCPCC4AeM'

AXIO_MODELS = ['axio-fast', 'axio-terra', 'axio-pro']
BASELINE_MODELS = ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6-sol']

SUITES = {
    'mmmu_text_science':     {'cat': 'science',       'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'global_mmlu_lite':      {'cat': 'multilingual',  'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'flores_translation_instruction': {'cat': 'multilingual', 'fmt': 'open', 'qk': 'source', 'ak': 'reference'},
    'math_500':              {'cat': 'math',          'fmt': 'math', 'qk': 'prompt',   'ak': 'answer'},
    'aime_recent':           {'cat': 'math',          'fmt': 'math', 'qk': 'prompt',   'ak': 'answer'},
    'arc_challenge':         {'cat': 'logic',         'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'bbh':                   {'cat': 'logic',         'fmt': 'open', 'qk': 'prompt',   'ak': 'answer'},
    'truthfulqa':            {'cat': 'hallucination', 'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'halueval':              {'cat': 'hallucination', 'fmt': 'open', 'qk': 'prompt',   'ak': 'answer'},
    'medqa_usmle':           {'cat': 'vertical',      'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'legalbench':            {'cat': 'vertical',      'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'bizbench':              {'cat': 'vertical',      'fmt': 'code', 'qk': 'prompt',   'ak': 'answer'},
    'financebench':          {'cat': 'vertical',      'fmt': 'open', 'qk': 'prompt',   'ak': 'answer'},
    'policyllm_policybench': {'cat': 'vertical',      'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
}

# ── scoring (same as v3) ──
def extract_math_answer(text):
    t = str(text).strip()
    m = re.findall(r'\\boxed\{([^}]+)\}', t)
    if m: return m[-1].strip()
    m = re.findall(r'(?:answer|Answer)[^:]*[:=]\s*([^\n.,;]+)', t)
    if m: return m[-1].strip()
    nums = re.findall(r'-?\d+(?:\.\d+)?', t)
    if nums: return nums[-1]
    return t

def norm_math(s):
    return str(s).strip().replace(',','').replace('$','').replace('%','').replace(' ','').lower()

def score_math(pred, gold):
    p = extract_math_answer(pred); g = str(gold).strip()
    pn, gn = norm_math(p), norm_math(g)
    if pn == gn: return 1.0
    try:
        if abs(float(pn)-float(gn)) < 1e-4: return 1.0
        if float(gn) != 0 and abs(float(pn)-float(gn))/abs(float(gn)) < 1e-4: return 1.0
    except: pass
    try:
        if '/' in pn and '/' in gn:
            a,b=pn.split('/'); c,d=gn.split('/')
            if abs(float(a)/float(b)-float(c)/float(d)) < 1e-4: return 1.0
    except: pass
    return 0.0

def score_mcq(pred, gold):
    p = str(pred).strip().upper()[:5]
    g = str(gold).strip().upper()
    for ch in p:
        if ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            return 1.0 if ch == g else 0.0
    if g.lower() in str(pred).lower()[:50]: return 1.0
    return 0.0

def score_open(pred, gold):
    p = str(pred).strip().lower()
    g = str(gold).strip().lower()
    if p == g: return 1.0
    if len(g) <= 5 and g in p.split(): return 1.0
    if len(g) > 5 and g in p: return 0.5
    return 0.0

def score_code(pred, gold):
    p = str(pred).strip()
    g = str(gold).strip()
    if not p or not g: return 0.0
    if g in p: return 1.0
    # 标准化空白后匹配
    pn = ' '.join(p.split())
    gn = ' '.join(g.split())
    if gn and gn in pn: return 1.0
    # 代码块提取后匹配
    import re
    blocks = re.findall(r'```(?:python)?\s*\n(.*?)\n```', p, re.DOTALL)
    for block in blocks:
        bn = ' '.join(block.split())
        if gn and gn in bn: return 1.0
    return 0.0

SCORERS = {'mcq': score_mcq, 'open': score_open, 'math': score_math, 'code': score_code}

def score(pred, gold, fmt):
    return SCORERS.get(fmt, score_open)(pred, gold)

# ── data ──
def load_suite(name):
    path = BENCH_DIR / f'{name}.jsonl'
    if not path.exists(): return []
    return [json.loads(l) for l in open(path) if l.strip()]

def build_prompt(case, meta):
    q = str(case.get(meta['qk'], ''))
    if meta['fmt'] == 'mcq':
        opts = case.get(meta.get('ok', 'options'), {})
        if isinstance(opts, str):
            return f'{q}\n\n{opts}\n\nAnswer with just the option letter.'
        olines = [f'{k}: {v}' for k, v in sorted(opts.items())] if isinstance(opts, dict) else [str(opts)]
        return f'{q}\n\nOptions:\n' + '\n'.join(olines) + '\n\nAnswer with just the option letter.'
    return q

# ── HTTP calls ──
def call_axio(model, prompt):
    body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 512, 'stream': False}).encode()
    req = urllib.request.Request(AXIO_URL, data=body, headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT_SEC)
        return json.loads(resp.read()).get('choices', [{}])[0].get('message', {}).get('content', '')
    except Exception as e:
        return None

def call_cpa(model, prompt):
    body = json.dumps({'model': model, 'input': prompt, 'max_output_tokens': 512,
        'reasoning': {'effort': 'max'}}).encode()
    req = urllib.request.Request(CPA_URL, data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {CPA_KEY}'})
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT_SEC)
        data = json.loads(resp.read())
        for item in data.get('output', []):
            if item.get('type') == 'message':
                for c in item.get('content', []):
                    if c.get('type') == 'output_text':
                        return c['text']
        return json.dumps(data)[:500]
    except Exception as e:
        return None

# ── Main ──
def main():
    import socket
    socket.setdefaulttimeout(65)
    os.environ['no_proxy'] = '127.0.0.1,localhost'
    
    # Load existing results
    if OUTPUT.exists():
        with open(OUTPUT) as f: results = json.load(f)
    else:
        results = {'runs': [], 'meta': {'samples': SAMPLES}}
    done = {(r['suite'], r['model']) for r in results['runs']}
    
    total = sum(1 for s in SUITES if load_suite(s)) * 6
    print(f'=== AXIO BENCHMARK v4 (concurrent) ===')
    print(f'Suites: {len(SUITES)}  Models: 6  Samples: {SAMPLES}  Timeout: {TIMEOUT_SEC}s  Workers: {MAX_WORKERS}')
    print(f'Done: {len(done)}  Total: ~{total}')
    
    for sname, meta in SUITES.items():
        cases = load_suite(sname)
        if not cases:
            print(f'[SKIP] {sname}: no data')
            continue
        sampled = random.sample(cases, min(SAMPLES, len(cases)))
        
        for model in AXIO_MODELS + BASELINE_MODELS:
            if (sname, model) in done: continue
            
            # Build prompts for all questions
            prompts = [(i, build_prompt(case, meta), str(case.get(meta['ak'], ''))) 
                       for i, case in enumerate(sampled)]
            
            print(f'\n[{sname}] {model} ({meta["cat"]}, {len(prompts)} cases)', flush=True)
            
            correct = 0.0; errors = 0; t0 = time.time()
            call_fn = call_cpa if model.startswith('gpt-') else call_axio
            
            # Parallel calls with total timeout
            futures = {}
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                for idx, prompt, gold in prompts:
                    futures[executor.submit(call_fn, model, prompt)] = (idx, prompt, gold)
                
                total_timeout = TIMEOUT_SEC + 10  # Per-call timeout + grace
                deadline = __import__('time').time() + total_timeout
                remaining = set(futures.keys())
                
                while remaining and __import__('time').time() < deadline:
                    done, remaining = wait(remaining, timeout=10, return_when=FIRST_COMPLETED)
                    for future in done:
                        idx, prompt, gold = futures[future]
                        try:
                            pred = future.result(timeout=5)
                            if pred is None:
                                errors += 1
                                sym = 'E'
                            else:
                                s = score(pred, gold, meta['fmt'])
                                correct += s
                                sym = '✓' if s >= 1.0 else ('~' if s >= 0.5 else '✗')
                            ps = str(pred or 'ERR')[:55].replace('\n', ' ').strip()
                            gs = str(gold)[:35].replace('\n', ' ').strip()
                            print(f'  [{idx+1}/{len(prompts)}] {sym} p={ps} | g={gs}', flush=True)
                        except (TimeoutError, Exception):
                            errors += 1
                            print(f'  [{idx+1}/{len(prompts)}] TIMEOUT/ERR', flush=True)
                
                # Any remaining are timed out
                for future in remaining:
                    idx, prompt, gold = futures[future]
                    errors += 1
                    print(f'  [{idx+1}/{len(prompts)}] TIMEOUT', flush=True)
            
            acc = correct / len(prompts)
            elapsed = time.time() - t0
            print(f'  → Acc: {acc:.1%} ({correct:.1f}/{len(prompts)}) {elapsed:.0f}s e{errors}', flush=True)
            results['runs'].append({'suite': sname, 'model': model, 'accuracy': acc,
                'correct': correct, 'samples': len(prompts), 'errors': errors,
                'elapsed_s': round(elapsed, 1), 'time': time.strftime('%Y-%m-%d %H:%M:%S')})
            with open(OUTPUT, 'w') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Summary
    print('\n' + '=' * 80 + '\nFINAL RESULTS')
    ms = defaultdict(lambda: defaultdict(list))
    for r in results['runs']:
        ms[r['model']][SUITES.get(r['suite'], {}).get('cat', '?')].append(r['accuracy'])
    cats = sorted(set(c for m in ms.values() for c in m))
    hdr = f'{"Model":20s} {"Overall":>8s}' + ''.join(f' {c:>14s}' for c in cats)
    print(hdr + '\n' + '-' * len(hdr))
    for m in AXIO_MODELS + BASELINE_MODELS:
        cs = ms.get(m, {})
        alls = [s for ss in cs.values() for s in ss]
        ov = sum(alls) / len(alls) if alls else 0
        row = f'{m:20s} {ov:7.1%}'
        for c in cats:
            vals = cs.get(c, [])
            row += f' {sum(vals)/len(vals):13.1%}' if vals else f' {"N/A":>13s}'
        print(row)
    
    print('\n── Fusion vs Baseline ──')
    for am, bm in [('axio-pro', 'gpt-5.6-sol'), ('axio-terra', 'gpt-5.6-terra'), ('axio-fast', 'gpt-5.6-luna')]:
        as_ = [r['accuracy'] for r in results['runs'] if r['model'] == am]
        bs_ = [r['accuracy'] for r in results['runs'] if r['model'] == bm]
        if as_ and bs_:
            aa, bb = sum(as_)/len(as_), sum(bs_)/len(bs_)
            delta = aa - bb
            sym = '▲' if delta > 0 else ('▼' if delta < 0 else '=')
            print(f'{am} vs {bm}: {sym} {delta:+.1%} ({aa:.1%} vs {bb:.1%})')
    
    print(f'\n→ {OUTPUT}')

if __name__ == '__main__':
    main()
