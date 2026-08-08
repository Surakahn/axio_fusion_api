#!/usr/bin/env python3
"""
Axio Fusion Benchmark v2 — LLM-as-Judge for text benchmarks, larger samples.
"""
import json, os, sys, time, re, random, urllib.request
from pathlib import Path
from typing import Any

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
MAX_TOK = 512
SAMPLES = 10
JUDGE_MODEL = 'gpt-5.6-terra'  # Use terra for judging (cost-effective)

random.seed(42)

SUITES = [
    # (file, category, type, use_llm_judge)
    ('math_500.jsonl', 'Math', 'math', False),
    ('aime_recent.jsonl', 'Math', 'math', False),
    ('arc_challenge.jsonl', 'Logic', 'mcq', False),
    ('truthfulqa.jsonl', 'Hallucination', 'mcq', False),
    ('mmmu_text_science.jsonl', 'Science', 'mcq', False),
    ('medqa_usmle.jsonl', 'Science', 'mcq', False),
    ('global_mmlu_lite.jsonl', 'DailyWork', 'mcq', False),
    ('legalbench.jsonl', 'Vertical', 'mcq', False),
    ('financebench.jsonl', 'Vertical', 'text', True),   # LLM judge
    ('bizbench.jsonl', 'Vertical', 'mcq', False),
    ('policyllm_policybench.jsonl', 'Vertical', 'mcq', False),
    ('flores_translation_instruction.jsonl', 'Multilingual', 'text', True),  # LLM judge
    ('halueval.jsonl', 'Hallucination', 'mcq', False),
    ('bbh.jsonl', 'Logic', 'text', True),  # LLM judge
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

def score_exact(pred, gold, ttype):
    if not pred or not gold: return 0.0
    p, g = extract(pred, ttype), extract(gold, ttype)
    if not p or not g: return 0.0
    if ttype == 'mcq': return 1.0 if p[0].upper() == g[0].upper() else 0.0
    if ttype == 'math':
        try: return 1.0 if abs(float(p.replace(',','')) - float(g.replace(',',''))) < 1e-4 else 0.0
        except: return 1.0 if p.strip().lower() == g.strip().lower() else 0.0
    return 1.0 if p.strip().lower() == g.strip().lower() else 0.0

def call_cpa_raw(model, prompt, max_tok=300):
    """Direct CPA call - used for both baselines and LLM judge."""
    for attempt in range(3):
        try:
            payload = json.dumps({'model':model,'input':prompt,'max_output_tokens':max_tok}).encode()
            req = urllib.request.Request(f'{CPA_URL}/responses', data=payload,
                headers={'Authorization':f'Bearer {CPA_KEY}','Content-Type':'application/json','User-Agent':'AxioFusionAPI/1.0'})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read())
            text = ''
            for o in data.get('output',[]):
                if o.get('type')=='message':
                    for c in o.get('content',[]):
                        if c.get('type')=='output_text': text += c.get('text','')
            if text.strip(): return text
        except Exception as e:
            if attempt < 2: time.sleep(2)
    return f"ERROR"

def llm_judge_score(question, prediction, reference):
    """Use LLM as judge for text-type benchmarks."""
    prompt = f"""You are evaluating a model's answer against a reference answer.

Question: {question[:2000]}

Model's Answer: {prediction[:2000]}

Reference Answer: {reference[:2000]}

Is the model's answer CORRECT (matches the reference in meaning/facts) or INCORRECT?
Reply with exactly one word: CORRECT or INCORRECT."""
    
    text = call_cpa_raw(JUDGE_MODEL, prompt, max_tok=10)
    return 1.0 if text.strip().upper().startswith('CORRECT') else 0.0

def call_axio(engine, policy, model, prompt, max_tok=300):
    for attempt in range(3):
        try:
            req = FusionRequest(model=model, prompt=prompt, policy=policy, max_output_tokens=max_tok)
            resp = engine.complete(req)
            if resp.text.strip():
                return resp.text, resp.route_plan.get('strategy','?')
        except Exception as e:
            if attempt < 2: time.sleep(3)
    return f"ERROR", 'error'

def run_suite(engine, policy, bench_file, cat, dtype, use_judge, samples):
    path = BENCH_DIR / bench_file
    if not path.exists():
        print(f"SKIP {bench_file}", flush=True); return None
    
    with open(path) as f:
        items = [json.loads(l) for l in f if l.strip()]
    n = min(samples, len(items))
    items = random.sample(items, n)
    
    print(f"\n{'='*50}\n  {bench_file} [{cat}] n={n} judge={'Y' if use_judge else 'N'}\n{'='*50}", flush=True)
    
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
            prompt = f"{q}\n\nShow work. Put final answer in \\boxed{{}}."
        else:
            prompt = q
        
        predictions = {}
        for model in ALL_M:
            if model in AXIO:
                text, strat = call_axio(engine, policy, model, prompt, MAX_TOK)
            else:
                text = call_cpa_raw(model, prompt, MAX_TOK)
                strat = 'direct_cpa'
            predictions[model] = (text, strat)
        
        for model in ALL_M:
            text, strat = predictions[model]
            if text.startswith('ERROR'):
                s = -1
            elif use_judge:
                s = llm_judge_score(q, text, gold)
            else:
                s = score_exact(text, gold, dtype)
            scores[model].append(s)
            err = f" ERR:{text[:40]}" if text.startswith('ERROR') else ""
            flag = '✓' if s>0 else ('✗' if s==0 else '⚠')
            print(f"  [{idx+1}/{n}] {model:16s} {flag} [{strat:25s}] s={s:.2f}{err}", flush=True)
    
    # Summary
    print(f"\n  --- {bench_file} ---", flush=True)
    result = {'bench_file': bench_file, 'cat': cat, 'n': n, 'use_judge': use_judge}
    for m in ALL_M:
        v = [s for s in scores[m] if s>=0]
        avg = sum(v)/len(v) if v else 0
        result[m] = {'avg': round(avg,4), 'n_valid': len(v), 'errors': sum(1 for s in scores[m] if s<0)}
        print(f"  {m:16s}: {avg:.3f} (n={len(v)})", flush=True)
    
    for ax,ba in [('axio-fast','gpt-5.6-luna'),('axio-terra','gpt-5.6-terra'),('axio-pro','gpt-5.6-sol')]:
        av = sum(s for s in scores[ax] if s>=0)/max(1,sum(1 for s in scores[ax] if s>=0))
        bv = sum(s for s in scores[ba] if s>=0)/max(1,sum(1 for s in scores[ba] if s>=0))
        f = 'WIN' if av>bv else ('LOSE' if av<bv else 'TIE')
        result[f'{ax}_vs_{ba}'] = {'result': f, 'axio': round(av,4), 'baseline': round(bv,4)}
        print(f"  {ax} vs {ba}: {f} ({av:.3f} vs {bv:.3f})", flush=True)
    
    return result

def main():
    # Setup
    print("Creating engine...", flush=True)
    profiles = load_registry(REG_PATH, require_prefusion=False)
    client = HTTPProviderClient(require_streaming=True)
    engine = FusionEngine(profiles, client=client)
    policy = FusionPolicy(live=True)
    
    # Pre-warm
    print("Pre-warming...", flush=True)
    for m in ['axio-fast', 'axio-terra', 'axio-pro']:
        for attempt in range(3):
            try:
                r = engine.complete(FusionRequest(model=m, prompt='hi', policy=policy, max_output_tokens=5))
                print(f"  {m}: OK", flush=True); break
            except:
                if attempt < 2: time.sleep(3)
                else: print(f"  {m}: FAIL", flush=True)
    
    results = {}
    wins = losses = ties = 0
    
    for bench_file, cat, dtype, use_judge in SUITES:
        r = run_suite(engine, policy, bench_file, cat, dtype, use_judge, SAMPLES)
        if r:
            results[bench_file] = r
            for ax,ba in [('axio-fast','gpt-5.6-luna'),('axio-terra','gpt-5.6-terra'),('axio-pro','gpt-5.6-sol')]:
                key = f'{ax}_vs_{ba}'
                if key in r:
                    if r[key]['result'] == 'WIN': wins += 1
                    elif r[key]['result'] == 'LOSE': losses += 1
                    else: ties += 1
        
        # Save incremental
        total = wins+losses+ties
        out = {'wins': wins, 'losses': losses, 'ties': ties, 'total': total, 'results': results}
        with open('/tmp/bench_v2_results.json', 'w') as f:
            json.dump(out, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"FINAL: {wins}W {losses}L {ties}T / {wins+losses+ties}")
    print(f"{'='*50}")
    
    out = {'wins': wins, 'losses': losses, 'ties': ties, 'total': wins+losses+ties, 'results': results}
    with open('/tmp/bench_v2_results.json', 'w') as f:
        json.dump(out, f, indent=2)
    print("Saved to /tmp/bench_v2_results.json")

if __name__ == '__main__':
    main()
