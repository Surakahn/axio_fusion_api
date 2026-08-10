#!/usr/bin/env python3
"""Axio Fusion Benchmark v3 — subprocess+stdin, flexible scoring, 14 suites."""
import os, sys, json, time, random, re, subprocess
from pathlib import Path
from collections import defaultdict

BENCH_DIR = Path('/mnt/storage/axio_fusion_benchmarks/standardized')
OUTPUT = Path('/home/he/axio_fusion_api/private/bench_results_v3.json')
WORKER = '/home/he/axio_fusion_api/scripts/_bench_worker.py'
PYTHON = '/home/he/axio_fusion_api/.venv/bin/python'
SAMPLES = 8
TIMEOUT_SEC = 60

AXIO_MODELS = ['axio-fast', 'axio-terra', 'axio-pro']
BASELINE_MODELS = ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6-sol']

SUITES = {
    'mmmu_text_science':     {'cat': 'science',       'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'global_mmlu_lite':      {'cat': 'multilingual',  'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'flores_translation_instruction': {'cat': 'multilingual', 'fmt': 'open', 'qk': 'prompt', 'ak': 'answer'},
    'math_500':              {'cat': 'math',          'fmt': 'math', 'qk': 'prompt',   'ak': 'answer'},
    'aime_recent':           {'cat': 'math',          'fmt': 'math', 'qk': 'prompt',   'ak': 'answer'},
    'arc_challenge':         {'cat': 'logic',         'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'bbh':                   {'cat': 'logic',         'fmt': 'open', 'qk': 'prompt',   'ak': 'answer'},
    'truthfulqa':            {'cat': 'hallucination', 'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'halueval':              {'cat': 'hallucination', 'fmt': 'open', 'qk': 'prompt',   'ak': 'answer'},
    'medqa_usmle':           {'cat': 'vertical',      'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'legalbench':            {'cat': 'vertical',      'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'bizbench':              {'cat': 'vertical',      'fmt': 'open', 'qk': 'prompt',   'ak': 'answer'},
    'financebench':          {'cat': 'vertical',      'fmt': 'open', 'qk': 'prompt',   'ak': 'answer'},
    'policyllm_policybench': {'cat': 'vertical',      'fmt': 'mcq',  'qk': 'question', 'ok': 'options', 'ak': 'answer'},
}

# ── Scoring ─────────────────────────────────────────────
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
        pv, gv = float(pn), float(gn)
        if abs(pv-gv) < 1e-4: return 1.0
        if gv != 0 and abs(pv-gv)/abs(gv) < 1e-4: return 1.0
    except: pass
    try:
        if '/' in pn and '/' in gn:
            a,b=pn.split('/'); c,d=gn.split('/')
            if abs(float(a)/float(b)-float(c)/float(d)) < 1e-4: return 1.0
    except: pass
    return 0.0

def score_mcq(pred, gold):
    p, g = str(pred).strip(), str(gold).strip()
    m = re.findall(r'\b([A-Ea-e])\b', p)
    if m: return 1.0 if m[0].upper() == g[:1].upper() else 0.0
    return 1.0 if p[:1].upper() == g[:1].upper() else 0.0

def score_open(pred, gold):
    p, g = str(pred).lower().strip(), str(gold).lower().strip()
    if p == g: return 1.0
    if len(g) > 10 and g in p: return 1.0
    if len(p) > 10 and p in g: return 1.0
    pw, gw = set(p.split()), set(g.split())
    if not gw: return 0.0
    overlap = len(pw & gw) / len(gw)
    return 1.0 if overlap > 0.7 else (0.5 if overlap > 0.4 else 0.0)

def score(pred, gold, fmt):
    if not pred or not gold: return 0.0
    if fmt == 'mcq':  return score_mcq(pred, gold)
    if fmt == 'math': return score_math(pred, gold)
    if fmt == 'open': return score_open(pred, gold)
    return 1.0 if str(pred).strip().lower() == str(gold).strip().lower() else 0.0

# ── Model calling ───────────────────────────────────────
def call_model(model, prompt):
    """Call subprocess worker with prompt via stdin."""
    mode = 'cpa' if model.startswith('gpt-') else 'axio'
    cmd = [PYTHON, WORKER, '--mode', mode, '--model', model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, input=prompt,
                          timeout=TIMEOUT_SEC,
                          env={**os.environ, 'no_proxy': '127.0.0.1,localhost'})
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), None
        err = r.stderr[:200] if r.stderr else ''
        return '', f'RC{r.returncode}: {err}' if err else f'RC{r.returncode} empty'
    except subprocess.TimeoutExpired:
        return '', 'TIMEOUT'
    except Exception as e:
        return '', f'{type(e).__name__}: {str(e)[:100]}'

# ── Data I/O ────────────────────────────────────────────
def load_suite(name):
    path = BENCH_DIR / f'{name}.jsonl'
    if not path.exists(): return []
    return [json.loads(l) for l in open(path) if l.strip()]

def build_prompt(case, meta):
    q = str(case.get(meta['qk'], ''))
    if meta['fmt'] == 'mcq':
        opts = case.get(meta.get('ok', 'options'), {})
        if isinstance(opts, str):
            try: opts = json.loads(opts)
            except:
                try: opts = eval(opts)
                except: opts = {}
        if isinstance(opts, dict):
            olines = '\n'.join(f'{k}: {v}' for k, v in sorted(opts.items()))
        elif isinstance(opts, list):
            labels = [chr(65+i) for i in range(len(opts))]
            olines = '\n'.join(f'{l}: {o}' for l, o in zip(labels, opts))
        else:
            olines = str(opts)
        return f'{q}\n\nOptions:\n{olines}\n\nAnswer with just the option letter.'
    return q

def load_results():
    if OUTPUT.exists():
        with open(OUTPUT) as f: return json.load(f)
    return {'runs': [], 'meta': {'samples': SAMPLES}}

def save_results(r):
    with open(OUTPUT, 'w') as f:
        json.dump(r, f, indent=2, ensure_ascii=False)

# ── Main ─────────────────────────────────────────────────
def main():
    results = load_results()
    done = {(r['suite'], r['model']) for r in results['runs']}
    total = sum(1 for s in SUITES if load_suite(s)) * 6
    
    print(f'=== AXIO BENCHMARK v3 ===')
    print(f'Suites: {len(SUITES)}  Models: 6  Samples: {SAMPLES}  Timeout: {TIMEOUT_SEC}s')
    print(f'Done: {len(done)}  Total: ~{total}')
    
    for sname, meta in SUITES.items():
        cases = load_suite(sname)
        if not cases:
            print(f'[SKIP] {sname}: no data')
            continue
        sampled = random.sample(cases, min(SAMPLES, len(cases)))
        for model in AXIO_MODELS + BASELINE_MODELS:
            if (sname, model) in done: continue
            tag = meta['cat'][:8]
            print(f'\n[{sname}] {model} ({tag}, {len(sampled)} cases)', flush=True)
            correct = 0.0; errors = 0; t0 = time.time()
            for i, case in enumerate(sampled):
                prompt = build_prompt(case, meta)
                gold = str(case.get(meta['ak'], ''))
                pred, err = call_model(model, prompt)
                if err:
                    errors += 1
                    print(f'  [{i+1}/{len(sampled)}] ERR: {err[:80]}', flush=True)
                else:
                    s = score(pred, gold, meta['fmt'])
                    correct += s
                    sym = '✓' if s>=1.0 else ('~' if s>=0.5 else '✗')
                    ps = str(pred)[:55].replace('\n',' ').strip()
                    gs = str(gold)[:35].replace('\n',' ').strip()
                    print(f'  [{i+1}/{len(sampled)}] {sym} p={ps} | g={gs}', flush=True)
            acc = correct/len(sampled); elapsed = time.time()-t0
            print(f'  → Acc: {acc:.1%} ({correct:.1f}/{len(sampled)}) {elapsed:.0f}s', flush=True)
            results['runs'].append({'suite':sname,'model':model,'accuracy':acc,
                'correct':correct,'samples':len(sampled),'errors':errors,
                'elapsed_s':round(elapsed,1),'time':time.strftime('%Y-%m-%d %H:%M:%S')})
            save_results(results)
    
    # Summary
    print('\n'+'='*80+'\nFINAL RESULTS')
    ms = defaultdict(lambda: defaultdict(list))
    for r in results['runs']:
        ms[r['model']][SUITES.get(r['suite'],{}).get('cat','?')].append(r['accuracy'])
    cats = sorted(set(c for m in ms.values() for c in m))
    hdr = f'{"Model":20s} {"Overall":>8s}'+''.join(f' {c:>14s}' for c in cats)
    print(hdr+'\n'+'-'*len(hdr))
    for m in AXIO_MODELS+BASELINE_MODELS:
        cs=ms.get(m,{}); alls=[s for ss in cs.values() for s in ss]
        ov=sum(alls)/len(alls) if alls else 0
        row=f'{m:20s} {ov:7.1%}'
        for c in cats: row+=f' {sum(cs.get(c,[0]))/len(cs[c]):13.1%}' if cs.get(c) else f' {"N/A":>13s}'
        print(row)
    
    print('\n── Fusion vs Baseline ──')
    for am,bm in [('axio-pro','gpt-5.6-sol'),('axio-terra','gpt-5.6-terra'),('axio-fast','gpt-5.6-luna')]:
        as_=[r['accuracy'] for r in results['runs'] if r['model']==am]
        bs_=[r['accuracy'] for r in results['runs'] if r['model']==bm]
        if as_ and bs_:
            aa,ba=sum(as_)/len(as_),sum(bs_)/len(bs_)
            d=aa-ba; sym='▲' if d>0 else ('▼' if d<0 else '=')
            print(f'{am} vs {bm}: {sym} {d:+.1%} ({aa:.1%} vs {ba:.1%})')
    
    save_results(results); print(f'\n→ {OUTPUT}')

if __name__ == '__main__':
    main()
