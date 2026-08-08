#!/usr/bin/env python3
"""Direct FusionEngine evaluation: axio-* vs single-model baselines.
Uses FusionEngine directly (no HTTP) for reliability and speed.
"""
import os, sys, json, time, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

os.environ['AXIO_FUSION_REGISTRY_PATH'] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'private/current_channel_enrollment_20260728_combined_r1/runtime_registry.calibrated.private.json'
)

from axio_fusion_api.registry import load_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.providers import HTTPProviderClient
from axio_fusion_api.schemas import FusionRequest

# Also load CPA key for baseline
env_file = os.path.join(os.path.dirname(__file__), '..', 'private/current_channels.env')
if os.path.exists(env_file):
    for line in open(env_file):
        if line.startswith('export '):
            k, v = line[7:].strip().split('=', 1)
            os.environ[k] = v.strip('"').strip("'")

import urllib.request
CPA_BASE = os.environ.get('AXIO_CPA_PLUS_BASE_URL', 'https://cpa.co6.click/v1')
CPA_KEY = os.environ.get('AXIO_CPA_PLUS_API_KEY', '')

SAMPLES = 5  # Per benchmark per model

# ── Provider helpers ───────────────────────────────────────────────────────
proxy_handler = urllib.request.ProxyHandler({
    'http': 'http://127.0.0.1:10808',
    'https': 'http://127.0.0.1:10808',
})
opener = urllib.request.build_opener(proxy_handler)

def call_cpa(model, prompt, reasoning='max'):
    payload = json.dumps({
        'model': model, 'input': [{'role': 'user', 'content': prompt}],
        'max_output_tokens': 256, 'temperature': 0.0,
        'reasoning': {'effort': reasoning},
    }).encode()
    req = urllib.request.Request(f'{CPA_BASE}/responses', data=payload, headers={
        'Content-Type': 'application/json', 'Authorization': f'Bearer {CPA_KEY}',
        'User-Agent': 'AxioFusionStandalone/0.1',
    })
    try:
        resp = opener.open(req, timeout=60)
        body = json.loads(resp.read().decode())
        for item in body.get('output', []):
            if item.get('type') == 'message':
                for c in item.get('content', []):
                    if c.get('type') == 'output_text':
                        return c['text']
        return ''
    except Exception as e:
        return f'[ERR:{e}]'

# ── Scoring ─────────────────────────────────────────────────────────────────
def score_mcq(response, ground_truth):
    resp_letter = re.search(r'[A-E]', response.strip().upper())
    gt_letter = re.search(r'[A-E]', ground_truth.strip().upper())
    if resp_letter and gt_letter:
        return 1.0 if resp_letter.group(0) == gt_letter.group(0) else 0.0
    return 1.0 if response.strip().lower() == ground_truth.strip().lower() else 0.0

def score_math(response, ground_truth):
    resp_nums = re.findall(r'-?\d+\.?\d*', response)
    gt_nums = re.findall(r'-?\d+\.?\d*', ground_truth)
    if not resp_nums or not gt_nums:
        return 1.0 if 'yes' in response.lower() and 'yes' in ground_truth.lower() else 0.0
    try: return 1.0 if abs(float(resp_nums[-1]) - float(gt_nums[-1])) < 1e-4 else 0.0
    except: return 0.0

def score_code(response, gt):
    if not response or len(response) < 10: return 0.0
    inds = ['def ', 'return ', 'import ', 'class ', 'print(']
    return min(1.0, sum(1 for i in inds if i in response) / 3.0)

# ── Benchmarks ──────────────────────────────────────────────────────────────
BENCHMARKS = [
    ('math_500.jsonl', 'Math-MATH500', 'math',
     lambda r: f"Solve: {r.get('problem','')}\nOutput only the final answer.",
     lambda r: str(r.get('answer',''))),
    ('humaneval.jsonl', 'Code-HumanEval', 'code',
     lambda r: f"Complete this Python function:\n{r.get('prompt','')}\nOutput only the completed code.",
     lambda r: str(r.get('canonical_solution',''))),
    ('arc_challenge.jsonl', 'Logic-ARC', 'mcq',
     lambda r: f"Q: {r.get('question','')}\n{r.get('choices',{}).get('text','')}\nAnswer letter only.",
     lambda r: str(r.get('answerKey',''))),
    ('truthfulqa.jsonl', 'Hallucination-TruthfulQA', 'mcq',
     lambda r: f"Q: {r.get('question','')}\nAnswer truthfully, letter only.",
     lambda r: str(r.get('best_answer','A'))),
    ('global_mmlu_lite.jsonl', 'Science-MMLU', 'mcq',
     lambda r: f"Q: {r.get('question','')}\n{r.get('choices',[])}\nAnswer letter only.",
     lambda r: str(r.get('answer',''))),
    ('medqa_usmle.jsonl', 'Medical-MedQA', 'mcq',
     lambda r: f"Medical Q: {r.get('question','')}\nA:{r.get('opa','')} B:{r.get('opb','')} C:{r.get('opc','')} D:{r.get('opd','')}\nAnswer letter.",
     lambda r: str(r.get('answer',''))),
    ('finqa.jsonl', 'Finance-FinQA', 'math',
     lambda r: f"Finance Q: {r.get('question','')}\nAnswer with number.",
     lambda r: str(r.get('answer',''))),
    ('legalbench.jsonl', 'Legal-LegalBench', 'mcq',
     lambda r: f"Legal Q: {r.get('question','')}\n{r.get('choices',[])}\nAnswer letter.",
     lambda r: str(r.get('answer',''))),
]

MODELS = {
    'axio-fast': {'baseline': 'gpt-5.6-luna', 'reasoning': 'max'},
    'axio-terra': {'baseline': 'gpt-5.6-terra', 'reasoning': 'max'},
    'axio-pro': {'baseline': 'gpt-5.6-sol', 'reasoning': 'max'},
}

# ── Run ─────────────────────────────────────────────────────────────────────
profiles = load_registry(require_prefusion=False)
engine = FusionEngine(profiles, client=HTTPProviderClient(require_streaming=True))

print(f"=== Direct FusionEngine Evaluation ===", flush=True)
print(f"Samples/benchmark: {SAMPLES}, Benchmarks: {len(BENCHMARKS)}", flush=True)
print(f"Models: {list(MODELS.keys())}", flush=True)

all_results = {}
total_start = time.time()

for filename, label, btype, fmt_fn, ans_fn in BENCHMARKS:
    path = os.path.join('data/benchmarks', filename)
    if not os.path.exists(path):
        print(f"\n[{label}] SKIP: file not found", flush=True)
        continue
    
    records = [json.loads(l) for l in open(path).readlines()[:SAMPLES]]
    print(f"\n[{label}] {len(records)} samples", flush=True)
    all_results[label] = {}
    
    for axio_model, cfg in MODELS.items():
        baseline_model = cfg['baseline']
        
        for model_tag, call_fn in [
            (axio_model, lambda p: engine.complete(FusionRequest(
                model=axio_model, prompt=p, task_type='auto',
                requested_capabilities=[], api_format='chat/completions',
                max_output_tokens=512), live=True).text),
            (baseline_model, lambda p: call_cpa(baseline_model, p, cfg['reasoning'])),
        ]:
            scores = []
            times = []
            for r in records:
                prompt = fmt_fn(r)
                gt = ans_fn(r)
                t0 = time.time()
                resp = call_fn(prompt)
                elapsed = time.time() - t0
                if resp and not resp.startswith('[ERR:'):
                    s = score_mcq(resp, gt) if btype == 'mcq' else (
                        score_math(resp, gt) if btype == 'math' else score_code(resp, gt))
                    scores.append(s)
                    times.append(elapsed)
            
            avg_s = sum(scores)/len(scores) if scores else 0
            avg_t = sum(times)/len(times) if times else 0
            all_results[label][model_tag] = {'score': round(avg_s, 3), 'latency': round(avg_t, 1), 'n': len(scores)}
            print(f"  {model_tag:20s}: score={avg_s:.3f}  latency={avg_t:.1f}s  ({len(scores)}/{SAMPLES})", flush=True)

# ── Summary ─────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print(f"SUMMARY (elapsed: {time.time()-total_start:.0f}s)")
print(f"{'='*70}")

for axio_model, cfg in MODELS.items():
    baseline = cfg['baseline']
    axio_scores = [all_results[l][axio_model]['score'] for l in all_results if axio_model in all_results.get(l,{})]
    base_scores = [all_results[l][baseline]['score'] for l in all_results if baseline in all_results.get(l,{})]
    
    if axio_scores and base_scores:
        axio_avg = sum(axio_scores)/len(axio_scores)
        base_avg = sum(base_scores)/len(base_scores)
        delta = axio_avg - base_avg
        axio_lat = sum(all_results[l][axio_model]['latency'] for l in all_results if axio_model in all_results.get(l,{})) / len(axio_scores)
        base_lat = sum(all_results[l][baseline]['latency'] for l in all_results if baseline in all_results.get(l,{})) / len(base_scores)
        
        verdict = "🏆 AXIO WINS" if delta > 0 else ("🤝 TIE" if delta == 0 else "❌ BASELINE WINS")
        print(f"\n{axio_model} vs {baseline}:")
        print(f"  Score:  {axio_avg:.4f} vs {base_avg:.4f}  Δ={delta:+.4f}  {verdict}")
        print(f"  Latency: {axio_lat:.1f}s vs {base_lat:.1f}s  ratio={axio_lat/base_lat:.1f}x")
        if axio_lat/base_lat > 3.0:
            print(f"  ⚠️ LATENCY EXCEEDS 3x GUARD!")

# Save
out = f"data/evaluation_results/direct_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(all_results, open(out, 'w'), indent=2)
print(f"\nSaved: {out}")
