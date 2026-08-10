#!/usr/bin/env python3
"""Focused re-benchmark v2: verify axio-terra/fast improvements after deadline fixes."""
import json, subprocess, time, re, random, sys
from pathlib import Path

BENCH_DIR = Path('/mnt/storage/axio_fusion_benchmarks/standardized')
SAMPLES = 5

# halueval is actually MCQ format (has options field)
FOCUS = [
    ('legalbench', 'mcq'),
    ('financebench', 'open'),
    ('halueval', 'mcq'),
    ('aime_recent', 'math'),
    ('bizbench', 'open'),
    ('policyllm_policybench', 'mcq'),
]

def score(pred, gold, fmt):
    if not pred or not gold: return 0.0
    if fmt == 'mcq':
        m = re.findall(r'\b([A-Ea-e])\b', str(pred))
        return 1.0 if m and m[0].upper()==str(gold)[:1].upper() else (1.0 if str(pred)[:1].upper()==str(gold)[:1].upper() else 0.0)
    if fmt == 'math':
        t = str(pred).strip()
        m = re.findall(r'\\boxed\{([^}]+)\}', t)
        p = m[-1].strip() if m else t
        m = re.findall(r'(?:answer|Answer)[^:]*[:=]\s*([^\n.,;]+)', p)
        p = m[-1].strip() if m else p
        pn = p.replace(',','').replace('$','').replace(' ','').lower()
        gn = str(gold).replace(',','').replace('$','').replace(' ','').lower()
        if pn == gn: return 1.0
        try:
            if abs(float(pn)-float(gn)) < 1e-4: return 1.0
        except: pass
        return 0.0
    if fmt == 'open':
        p, g = str(pred).lower().strip(), str(gold).lower().strip()
        if p == g or (len(g)>10 and g in p) or (len(p)>10 and p in g): return 1.0
        pw, gw = set(p.split()), set(g.split())
        return 1.0 if gw and len(pw&gw)/len(gw) > 0.7 else (0.5 if gw and len(pw&gw)/len(gw) > 0.4 else 0.0)
    return 0.0

def call_model(model, prompt):
    mode = 'cpa' if model.startswith('gpt-') else 'axio'
    cmd = [sys.executable, '/home/he/axio_fusion_api/scripts/_bench_worker.py',
           '--mode', mode, '--model', model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, input=prompt, timeout=180)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), None
        return '', f'RC{r.returncode}:{r.stderr[-80:]}' if r.stderr else f'RC{r.returncode}'
    except subprocess.TimeoutExpired:
        return '', 'TIMEOUT'
    except Exception as e:
        return '', str(e)[:80]

pairs = [('axio-terra', 'gpt-5.6-terra'), ('axio-fast', 'gpt-5.6-luna')]
all_results = {}

for sname, fmt in FOCUS:
    path = BENCH_DIR / f'{sname}.jsonl'
    if not path.exists():
        print(f'[SKIP] {sname}')
        continue
    cases = [json.loads(l) for l in open(path) if l.strip()]
    sampled = random.sample(cases, min(SAMPLES, len(cases)))
    
    for am, bm in pairs:
        for model in [am, bm]:
            key = f'{sname}/{model}'
            if key in all_results: continue
            
            sys.stdout.write(f'\n[{sname}] {model} ')
            sys.stdout.flush()
            correct = 0.0; errors = 0; t0 = time.time()
            
            for i, case in enumerate(sampled):
                q = str(case.get('question', case.get('prompt', '')))
                gold = str(case.get('answer', ''))
                if fmt == 'mcq':
                    opts = case.get('options', {})
                    if isinstance(opts, str):
                        try: opts = eval(opts)
                        except: opts = {}
                    if isinstance(opts, dict):
                        olines = '\n'.join(f'{k}: {v}' for k,v in sorted(opts.items()))
                    else:
                        olines = str(opts)
                    prompt = f'{q}\n\nOptions:\n{olines}\n\nAnswer with just the option letter.'
                else:
                    prompt = q
                
                pred, err = call_model(model, prompt)
                if err:
                    errors += 1
                    sys.stdout.write('E')
                else:
                    s = score(pred, gold, fmt)
                    correct += s
                    sys.stdout.write('v' if s>=1 else ('~' if s>=0.5 else 'x'))
                sys.stdout.flush()
            
            acc = correct/len(sampled); elapsed = time.time()-t0
            all_results[key] = {'acc': acc, 'errs': errors, 'elapsed': elapsed}
            print(f' {acc:.0%} e{errors} {elapsed:.0f}s', flush=True)

# Summary
print('\n' + '='*60)
print('FOCUSED RERUN RESULTS (with TERRA 6.0x deadline)')
for am, bm in pairs:
    a_keys = sorted([k for k in all_results if k.startswith(f'{am}/')])
    b_keys = sorted([k for k in all_results if k.startswith(f'{bm}/')])
    a_accs = [all_results[k]['acc'] for k in a_keys]
    b_accs = [all_results[k]['acc'] for k in b_keys]
    aa = sum(a_accs)/len(a_accs) if a_accs else 0
    ba = sum(b_accs)/len(b_accs) if b_accs else 0
    dlt = aa-ba
    sym = 'BETTER' if dlt>0 else ('WORSE' if dlt<0 else 'TIED')
    print(f'\n{am} vs {bm}: {sym} {dlt:+.1%} ({aa:.1%} vs {ba:.1%})')
    for k in a_keys:
        sn = k.split('/')[0]
        bv = all_results.get(f'{sn}/{bm}', {})
        aacc = all_results[k]['acc']; bacc = bv.get('acc',0)
        aerr = all_results[k]['errs']
        print(f'  {sn:25s}: {aacc:.0%} vs {bacc:.0%} (e{aerr})')
