#!/usr/bin/env python3
"""
Axio Fusion Robust Benchmark Evaluation
Self-contained, retry-enabled, incremental-save.
Usage: PYTHONPATH=src .venv/bin/python scripts/benchmark_eval_robust.py
"""
import json, os, sys, time, re, random, urllib.request, traceback
from pathlib import Path
from typing import Any

# ── Environment setup ──
# Credentials must be injected by the operator or a secret manager. Never
# provide fallback values in a tracked benchmark script.
os.environ.setdefault('AXIO_CPA_PLUS_BASE_URL', '')
os.environ.setdefault('AXIO_CPA_PLUS_API_KEY', '')
os.environ.setdefault('AXIO_NVIDIA_BASE_URL', '')
os.environ.setdefault('AXIO_NVIDIA_API_KEYS', '')
os.environ.setdefault('AXIO_FUSION_NETWORK_MODE', 'off')
os.environ.setdefault('AXIO_FUSION_SYSTEM_PROXY', '')
os.environ.setdefault('AXIO_FUSION_REGISTRY_PATH',
    '/home/he/axio_fusion_api/private/runs/2026-08-08-provider-enrollment-r42/runtime_registry.candidate.private.json')
os.environ.setdefault('AXIO_FUSION_PROVIDER_CONFIG_FILE',
    '/home/he/axio_fusion_api/config/current_channels.example.json')
for v in 'HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy'.split():
    os.environ.pop(v, None)

sys.path.insert(0, '/home/he/axio_fusion_api/src')

from axio_fusion_api.schemas import FusionRequest, FusionPolicy
from axio_fusion_api.registry import load_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.providers import HTTPProviderClient

# ── Config ──
BENCH_DIR   = Path('/mnt/storage/axio_fusion_benchmarks/standardized')
REG_PATH    = os.environ['AXIO_FUSION_REGISTRY_PATH']
OUTPUT_DIR  = Path('/tmp/axio_bench_results_v4')
SAMPLES_PER = 10
CPA_URL     = os.environ['AXIO_CPA_PLUS_BASE_URL']
CPA_KEY     = os.environ['AXIO_CPA_PLUS_API_KEY']
TIMEOUT     = 90
MAX_RETRIES = 2

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
random.seed(42)

# ── Scoring ──
def extract_ans(text: str, ttype: str) -> str:
    if not text: return ""
    if text.strip().startswith('{'):
        try:
            d = json.loads(text.strip())
            if isinstance(d, dict) and 'answer' in d: text = str(d['answer'])
        except: pass
    if ttype == 'mcq':
        t = text.strip().upper()
        for p in [r'\(([A-J])\)', r'\b([A-J])\)', r'^([A-J])[\s\.\,\)]', r'\b([A-J])\b']:
            m = re.search(p, t); 
            if m: return m.group(1).upper()
        return t[:5]
    if ttype == 'math':
        for p in [r'\\boxed\{([^}]+)\}', r'\$\$([^$]+)\$\$', r'\\\[([^\]]+)\\\]']:
            ms = re.findall(p, text)
            if ms: return ms[-1].strip()
        nums = re.findall(r'-?\d+\.?\d*', text)
        return nums[-1] if nums else text.strip()
    return text.strip()

def score_pred(pred: str, gold: str, ttype: str) -> float:
    if not pred or not gold: return 0.0
    p, g = extract_ans(pred, ttype), extract_ans(gold, ttype)
    if not p or not g: return 0.0
    if ttype == "mcq": return 1.0 if p[0].upper() == g[0].upper() else 0.0
    if ttype == "code": return 1.0 if g.strip() in p.strip() else 0.0
    if ttype == 'math':
        try: return 1.0 if abs(float(p.replace(',','')) - float(g.replace(',',''))) < 1e-4 else 0.0
        except: return 1.0 if p.strip().lower() == g.strip().lower() else 0.0
    return 1.0 if p.strip().lower() == g.strip().lower() else 0.0

# ── Fresh engine per call ──
def make_engine():
    profiles = load_registry(REG_PATH, require_prefusion=False)
    client = HTTPProviderClient(require_streaming=True)
    return FusionEngine(profiles, client=client)

def call_axio_with_retry(model: str, prompt: str, max_tok: int = 300) -> tuple[str, str]:
    """Call Axio model with pre-warmed engine and same-engine retries.
    
    CRITICAL: The first call after creating a fresh FusionEngine+HTTPProviderClient
    always fails because the initial TCP connection to CPA Plus times out.
    We pre-warm the engine with a trivial call, then retry failed calls
    on the SAME engine (not a new one).
    """
    last_err = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            engine = make_engine()
            policy = FusionPolicy(live=True)
            # Pre-warm ALL models to establish TCP connections
            for warm_model in ['axio-fast', 'axio-terra', 'axio-pro']:
                try:
                    engine.complete(FusionRequest(
                        model=warm_model, prompt='hi', policy=policy, max_output_tokens=5))
                except Exception:
                    pass  # Pre-warm failure is non-fatal
            # Now make the actual call (retry on same engine)
            for sub_attempt in range(MAX_RETRIES + 1):
                try:
                    req = FusionRequest(model=model, prompt=prompt, policy=policy, max_output_tokens=max_tok)
                    resp = engine.complete(req)
                    text = resp.text
                    if text.strip():
                        return text, resp.route_plan.get('strategy', '?')
                    last_err = "empty_output"
                except Exception as e:
                    last_err = str(e)[:150]
                if sub_attempt < MAX_RETRIES:
                    time.sleep(3)
        except Exception as e:
            last_err = str(e)[:150]
        if attempt < MAX_RETRIES:
            time.sleep(5)
    return f"ERROR:{last_err}", 'error'

def call_cpa_with_retry(model: str, prompt: str, max_tok: int = 300) -> tuple[str, str]:
    """Call CPA Plus directly with retry."""
    last_err = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            payload = json.dumps({'model': model, 'input': prompt, 'max_output_tokens': max_tok}).encode()
            req = urllib.request.Request(f'{CPA_URL}/responses', data=payload,
                headers={'Authorization': f'Bearer {CPA_KEY}', 'Content-Type': 'application/json',
                         'User-Agent': 'AxioFusionAPI/1.0'})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = json.loads(r.read())
            text = ''
            for o in data.get('output', []):
                if o.get('type') == 'message':
                    for c in o.get('content', []):
                        if c.get('type') == 'output_text': text += c.get('text', '')
            if text.strip():
                return text, 'direct_cpa'
            last_err = "empty_output"
        except Exception as e:
            last_err = str(e)[:150]
        if attempt < MAX_RETRIES:
            time.sleep(2 * (attempt + 1))
    return f"ERROR:{last_err}", 'error'

# ── Benchmark suites ──
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
    ('bizbench.jsonl', 'Vertical', 'code'),
    ('policyllm_policybench.jsonl', 'Vertical', 'mcq'),
    ('flores_translation_instruction.jsonl', 'Multilingual', 'text'),
    ('halueval.jsonl', 'Hallucination', 'mcq'),
    ('bbh.jsonl', 'Logic', 'text'),
]

AXIO_MODELS  = ['axio-fast', 'axio-terra', 'axio-pro']
CPA_BASELINE = {'gpt-5.6-luna': 'axio-fast', 'gpt-5.6-terra': 'axio-terra', 'gpt-5.6-sol': 'axio-pro'}
ALL_MODELS   = AXIO_MODELS + list(CPA_BASELINE.keys())

# ── Main ──
def main():
    print(f"=== Axio Fusion Robust Benchmark ===", flush=True)
    print(f"Registry: {REG_PATH}", flush=True)
    print(f"Samples per benchmark: {SAMPLES_PER}", flush=True)
    print(f"Max retries: {MAX_RETRIES}", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    
    # Global pre-warm: establish connections for all three models
    print("Pre-warming all models...", flush=True)
    for warm_model in ['axio-fast', 'axio-terra', 'axio-pro']:
        try:
            engine = make_engine()
            policy = FusionPolicy(live=True)
            engine.complete(FusionRequest(model=warm_model, prompt='hi', policy=policy, max_output_tokens=5))
            print(f"  {warm_model}: OK", flush=True)
        except Exception as e:
            print(f"  {warm_model}: WARN {str(e)[:60]}", flush=True)
    print("Pre-warm complete", flush=True)
    
    summary = {}
    
    for bench_file, cat, dtype in SUITES:
        path = BENCH_DIR / bench_file
        if not path.exists():
            print(f"\nSKIP {bench_file}: not found", flush=True)
            continue
        
        with open(path) as f:
            items = [json.loads(l) for l in f if l.strip()]
        n = min(SAMPLES_PER, len(items))
        items = random.sample(items, n)
        
        print(f"\n{'='*55}\n  {bench_file} [{cat}] n={n}\n{'='*55}", flush=True)
        
        bench_scores = {m: [] for m in ALL_MODELS}
        
        for idx, item in enumerate(items):
            q = item.get('question', item.get('prompt', item.get('source', '')))
            gold = str(item.get('answer', item.get('reference', '')))
            
            if dtype == 'mcq' and 'options' in item:
                opts = '\n'.join(f'{chr(65+i)}. {o}' for i, o in enumerate(item['options']))
                prompt = f"{q}\n\n{opts}\n\nAnswer with just the letter."
            elif dtype == 'math':
                prompt = f"{q}\n\nShow work step by step. Put final answer in \\boxed{{}}."
            else:
                prompt = q
            
            for model in ALL_MODELS:
                if model in AXIO_MODELS:
                    text, strat = call_axio_with_retry(model, prompt)
                else:
                    text, strat = call_cpa_with_retry(model, prompt)
                
                s = score_pred(text, gold, dtype) if not text.startswith('ERROR:') else -1
                bench_scores[model].append(s)
                
                err = f" ERR:{text[:50]}" if text.startswith('ERROR:') else ""
                status = '✓' if s > 0 else ('✗' if s == 0 else '⚠')
                print(f"  [{idx+1}/{n}] {model:16s} {status} [{strat:25s}] s={s:.2f}{err}", flush=True)
            
            # Incremental save after each item
            agg = {m: (sum(v for v in bench_scores[m] if v >= 0) / max(1, sum(1 for v in bench_scores[m] if v >= 0)))
                   for m in ALL_MODELS}
            summary[bench_file] = {'cat': cat, 'agg': agg, 'n_done': idx + 1, 'n_total': n}
            with open(OUTPUT_DIR / f'{bench_file.replace(".jsonl","")}.json', 'w') as fh:
                json.dump({'cat': cat, 'n': n, 'idx': idx+1, 'agg': agg, 'scores': bench_scores}, fh, indent=2)
        
        # Per-benchmark aggregate
        print(f"\n  --- {bench_file} Summary ---", flush=True)
        for m in ALL_MODELS:
            valid = [v for v in bench_scores[m] if v >= 0]
            mean = sum(valid) / len(valid) if valid else 0.0
            errs = sum(1 for v in bench_scores[m] if v < 0)
            print(f"  {m:16s}: {mean:.3f} (n={len(valid)}, err={errs})", flush=True)
        
        for ax, ba in [('axio-fast','gpt-5.6-luna'),('axio-terra','gpt-5.6-terra'),('axio-pro','gpt-5.6-sol')]:
            av = summary[bench_file]['agg'][ax]
            bv = summary[bench_file]['agg'][ba]
            flag = '🟢 WIN' if av > bv else ('🔴 LOSE' if av < bv else '⚪ TIE')
            print(f"  {ax} vs {ba}: {flag} ({av:.3f} vs {bv:.3f})", flush=True)
    
    # ── Final tally ──
    print(f"\n{'='*55}\n  FINAL TALLY\n{'='*55}")
    wins = losses = ties = 0
    for bench_file, data in summary.items():
        agg = data['agg']
        for ax, ba in [('axio-fast','gpt-5.6-luna'),('axio-terra','gpt-5.6-terra'),('axio-pro','gpt-5.6-sol')]:
            if agg[ax] > agg[ba]: wins += 1
            elif agg[ax] < agg[ba]: losses += 1
            else: ties += 1
    
    total = wins + losses + ties
    if total:
        print(f"  Wins:   {wins}/{total} ({100*wins/total:.1f}%)")
        print(f"  Losses: {losses}/{total}")
        print(f"  Ties:   {ties}/{total}")
    
    with open(OUTPUT_DIR / 'final_summary.json', 'w') as f:
        json.dump({'wins': wins, 'losses': losses, 'ties': ties, 'summary': summary}, f, indent=2)
    print(f"\nResults saved to {OUTPUT_DIR}", flush=True)

if __name__ == '__main__':
    main()
