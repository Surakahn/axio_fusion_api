#!/usr/bin/env python3
"""Single-benchmark runner - one suite at a time, clean exit."""
import json, os, sys, time, re, random, urllib.request
from pathlib import Path

os.environ.setdefault('AXIO_CPA_PLUS_BASE_URL', 'https://cpa.co6.click/v1')
os.environ.setdefault('AXIO_CPA_PLUS_API_KEY', 'sk-S9APc6QARCPCC4AeM')
os.environ.setdefault('AXIO_NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1')
os.environ.setdefault('AXIO_NVIDIA_API_KEYS',
    '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')
os.environ.setdefault('AXIO_FUSION_NETWORK_MODE', 'off')
os.environ.setdefault('AXIO_FUSION_SYSTEM_PROXY', '')
os.environ.setdefault('AXIO_FUSION_REGISTRY_PATH',
    '/home/he/axio_fusion_api/private/runs/2026-08-08-provider-enrollment-r42/runtime_registry.candidate.private.json')
for v in 'HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy'.split():
    os.environ.pop(v, None)

sys.path.insert(0, '/home/he/axio_fusion_api/src')
from axio_fusion_api.schemas import FusionRequest, FusionPolicy
from axio_fusion_api.registry import load_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.providers import HTTPProviderClient

BENCH_DIR = Path('/mnt/storage/axio_fusion_benchmarks/standardized')
REG_PATH = os.environ['AXIO_FUSION_REGISTRY_PATH']
CPA_URL = 'https://cpa.co6.click/v1'
CPA_KEY = os.environ['AXIO_CPA_PLUS_API_KEY']
TIMEOUT = 90
MAX_TOK = 300

SUITES = [
    ('math_500.jsonl', 'Math', 'math'),
    ('aime_recent.jsonl', 'Math', 'math'),
    ('arc_challenge.jsonl', 'Logic', 'mcq'),
    ('truthfulqa.jsonl', 'Hallucination', 'mcq'),
    ('mmmu_text_science.jsonl', 'Science', 'mcq'),
    ('medqa_usmle.jsonl', 'Science', 'mcq'),
    ('global_mmlu_lite.jsonl', 'DailyWork', 'mcq'),
    ('legalbench.jsonl', 'Vertical', 'mcq'),
    ('financebench.jsonl', 'Vertical', 'text'),
    ('bizbench.jsonl', 'Vertical', 'mcq'),
    ('policyllm_policybench.jsonl', 'Vertical', 'mcq'),
    ('flores_translation_instruction.jsonl', 'Multilingual', 'text'),
    ('halueval.jsonl', 'Hallucination', 'mcq'),
    ('bbh.jsonl', 'Logic', 'text'),
]

def extract(text, ttype):
    if not text: return ""
    if text.strip().startswith('{'):
        try:
            d = json.loads(text.strip())
            if isinstance(d, dict) and 'answer' in d: text = str(d['answer'])
        except: pass
    if ttype == 'mcq':
        t = text.strip().upper()
        for p in [r'\(([A-J])\)', r'\b([A-J])\)', r'^([A-J])[\s\.\,\)]', r'\b([A-J])\b']:
            m = re.search(p, t)
            if m: return m.group(1).upper()
        return t[:5]
    if ttype == 'math':
        for p in [r'\\boxed\{([^}]+)\}', r'\$\$([^$]+)\$\$', r'\\\[([^\]]+)\\\]']:
            ms = re.findall(p, text)
            if ms: return ms[-1].strip()
        nums = re.findall(r'-?\d+\.?\d*', text)
        return nums[-1] if nums else text.strip()
    return text.strip()

def score(pred, gold, ttype):
    if not pred or not gold: return 0.0
    p, g = extract(pred, ttype), extract(gold, ttype)
    if not p or not g: return 0.0
    if ttype == 'mcq': return 1.0 if p[0].upper() == g[0].upper() else 0.0
    if ttype == 'math':
        try: return 1.0 if abs(float(p.replace(',','')) - float(g.replace(',',''))) < 1e-4 else 0.0
        except: return 1.0 if p.strip().lower() == g.strip().lower() else 0.0
    return 1.0 if p.strip().lower() == g.strip().lower() else 0.0

if __name__ == '__main__':
    bench_name = sys.argv[1] if len(sys.argv) > 1 else 'math_500.jsonl'
    bench_file = bench_name
    samples = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    # Find matching suite info
    si = next((s for s in SUITES if s[0]==bench_file), None)
    if not si:
        print(f"Unknown benchmark: {bench_file}"); sys.exit(1)
    _, cat, dtype = si
    
    path = BENCH_DIR / bench_file
    if not path.exists():
        print(f"SKIP {bench_file} - not found"); sys.exit(0)
    
    with open(path) as f:
        items = [json.loads(l) for l in f if l.strip()]
    n = min(samples, len(items))
    random.seed(42)
    items = random.sample(items, n)
    
    print(f"Creating engine for {bench_file}...", flush=True)
    profiles = load_registry(REG_PATH, require_prefusion=False)
    client = HTTPProviderClient(require_streaming=True)
    engine = FusionEngine(profiles, client=client)
    policy = FusionPolicy(live=True)
    
    # Pre-warm
    for m in ['axio-fast', 'axio-terra', 'axio-pro']:
        for attempt in range(3):
            try:
                r = engine.complete(FusionRequest(model=m, prompt='hi', policy=policy, max_output_tokens=5))
                print(f"  Pre-warm {m}: OK", flush=True)
                break
            except Exception as e:
                if attempt < 2: time.sleep(3)
                else: print(f"  Pre-warm {m}: FAIL", flush=True)
    
    print(f"\n{'='*50}\n  {bench_file} [{cat}] n={n}\n{'='*50}", flush=True)
    
    AXIO = ['axio-fast','axio-terra','axio-pro']
    BASELINES = {'gpt-5.6-luna':'axio-fast','gpt-5.6-terra':'axio-terra','gpt-5.6-sol':'axio-pro'}
    ALL_M = AXIO + list(BASELINES.keys())
    
    scores = {m: [] for m in ALL_M}
    for idx, item in enumerate(items):
        q = item.get('question', item.get('prompt', item.get('source','')))
        gold = str(item.get('answer', item.get('reference','')))
        if dtype == 'mcq' and 'options' in item:
            opts = '\n'.join(f'{chr(65+i)}. {o}' for i,o in enumerate(item['options']))
            prompt = f"{q}\n\n{opts}\n\nAnswer with just the letter."
        elif dtype == 'math':
            prompt = f"{q}\n\nShow work. Put answer in \\boxed{{}}."
        else:
            prompt = q
        
        for model in ALL_M:
            text, strat = '', 'error'
            for attempt in range(3):
                try:
                    if model in AXIO:
                        req = FusionRequest(model=model, prompt=prompt, policy=policy, max_output_tokens=MAX_TOK)
                        resp = engine.complete(req)
                        text = resp.text
                        strat = resp.route_plan.get('strategy','?')
                    else:
                        payload = json.dumps({'model':model,'input':prompt,'max_output_tokens':MAX_TOK}).encode()
                        req_obj = urllib.request.Request(f'{CPA_URL}/responses', data=payload,
                            headers={'Authorization':f'Bearer {CPA_KEY}','Content-Type':'application/json','User-Agent':'AxioFusionAPI/1.0'})
                        with urllib.request.urlopen(req_obj, timeout=TIMEOUT) as r:
                            data = json.loads(r.read())
                        text = ''
                        for o in data.get('output',[]):
                            if o.get('type')=='message':
                                for c in o.get('content',[]):
                                    if c.get('type')=='output_text': text += c.get('text','')
                        strat = 'direct_cpa'
                    if text.strip(): break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        text = f"ERROR:{e}"
                        strat = 'error'
            
            s = score(text, gold, dtype) if not text.startswith('ERROR:') else -1
            scores[model].append(s)
            err = f" ERR:{text[:50]}" if text.startswith('ERROR:') else ""
            flag = '✓' if s>0 else ('✗' if s==0 else '⚠')
            print(f"  [{idx+1}/{n}] {model:16s} {flag} [{strat:25s}] s={s:.2f}{err}", flush=True)
        
        # Save checkpoint every 2 items
        if (idx+1) % 2 == 0:
            out = {'cat':cat,'n':n,'done':idx+1,'bench_file':bench_file}
            for m in ALL_M:
                v = [s for s in scores[m] if s>=0]
                out[f'{m}_avg'] = sum(v)/len(v) if v else 0
                out[f'{m}_scores'] = scores[m]
            with open(f'/tmp/bench_single_{bench_file.replace(".jsonl","")}.json','w') as fh:
                json.dump(out, fh, indent=2)
    
    # Final results
    print(f"\n  --- {bench_file} ---", flush=True)
    for m in ALL_M:
        v = [s for s in scores[m] if s>=0]
        print(f"  {m:16s}: {sum(v)/len(v):.3f}" if v else f"  {m:16s}: N/A", flush=True)
    
    # Save final
    out = {'cat':cat,'n':n,'done':n,'bench_file':bench_file,'completed':True}
    for m in ALL_M:
        v = [s for s in scores[m] if s>=0]
        out[f'{m}_avg'] = sum(v)/len(v) if v else 0
        out[f'{m}_error_rate'] = sum(1 for s in scores[m] if s<0)/max(1,len(scores[m]))
        out[f'{m}_scores'] = scores[m]
    with open(f'/tmp/bench_single_{bench_file.replace(".jsonl","")}.json','w') as fh:
        json.dump(out, fh, indent=2)
    
    # Comparison
    for ax,ba in [('axio-fast','gpt-5.6-luna'),('axio-terra','gpt-5.6-terra'),('axio-pro','gpt-5.6-sol')]:
        av = sum(s for s in scores[ax] if s>=0)/max(1,sum(1 for s in scores[ax] if s>=0))
        bv = sum(s for s in scores[ba] if s>=0)/max(1,sum(1 for s in scores[ba] if s>=0))
        f = 'WIN' if av>bv else ('LOSE' if av<bv else 'TIE')
        print(f"  {ax} vs {ba}: {f} ({av:.3f} vs {bv:.3f})", flush=True)
    
    print(f"\nDONE {bench_file}", flush=True)
