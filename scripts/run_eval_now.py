#!/usr/bin/env python3
"""Axio Fusion - Quick evaluation with retry & proxy support."""
import json, os, time, re, urllib.request, hashlib
from pathlib import Path

AXIO_URL = "http://127.0.0.1:18900"
PROXY = "http://127.0.0.1:10808"
BENCHMARK_DIR = "data/benchmarks"
RESULTS_DIR = "data/evaluation_results"
MAX_SAMPLES = 15
TIMEOUT = 60

Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)

BENCHMARKS = [
    ("math_500.jsonl", "Math-MATH500", "math"),
    ("aime_recent.jsonl", "Math-AIME", "math"),
    ("humaneval.jsonl", "Code-HumanEval", "code"),
    ("arc_challenge.jsonl", "Logic-ARC", "mcq"),
    ("bbh.jsonl", "Logic-BBH", "mcq"),
    ("truthfulqa.jsonl", "Hallucination-TruthfulQA", "mcq"),
    ("halueval.jsonl", "Hallucination-HaluEval", "binary"),
    ("ifeval.jsonl", "DailyWork-IFEval", "instr"),
    ("global_mmlu_lite.jsonl", "Multilingual-GlobalMMLU", "mcq"),
    ("mmmu_text_science.jsonl", "Science-MMMU-Pro", "mcq"),
    ("medqa_usmle.jsonl", "Vertical-MedQA", "mcq"),
    ("finqa.jsonl", "Vertical-FinQA", "math"),
    ("legalbench.jsonl", "Vertical-LegalBench", "mcq"),
]

MODELS = ["axio-fast", "axio-terra"]

def call_axio(model, messages, max_tokens=256, retries=2):
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    data = json.dumps(payload).encode()
    proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(proxy_handler)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(f"{AXIO_URL}/v1/chat/completions", data=data, headers={"Content-Type": "application/json"})
            resp = opener.open(req, timeout=TIMEOUT)
            body = json.loads(resp.read().decode())
            return body["choices"][0]["message"]["content"], None
        except Exception as e:
            if attempt == retries:
                return None, str(e)[:200]
            time.sleep(2)
    return None, "max_retries"

def norm_ans(text):
    if not text: return ""
    text = str(text).strip().upper()
    for pat in [r'\bANSWER\s*(?:IS\s*)?[:\-]?\s*([A-J])\b', r'\b([A-J])\b\s*(?:is\s+correct)', r'\b([A-J])\)', r'^([A-J])[\s\.\,\)]', r'\b([A-J])\b']:
        m = re.search(pat, text, re.IGNORECASE)
        if m: return m.group(1).upper()
    return ""

def ext_math(text):
    if not text: return ""
    boxed = re.findall(r'\\boxed\{([^}]+)\}', str(text))
    if boxed: return boxed[-1].strip()
    for line in reversed(str(text).split('\n')):
        nums = re.findall(r'-?\d+\.?\d*', line.strip())
        if nums: return nums[-1]
    return str(text)

def norm_math(text):
    text = re.sub(r'[,%\$\s]', '', str(text).strip())
    try: return str(float(text))
    except: return text

def score(pred, gold, ttype):
    if not pred: return 0.0
    if ttype == "mcq":
        p, g = norm_ans(pred), norm_ans(str(gold))
        return 1.0 if p and g and p == g else 0.0
    elif ttype == "math":
        p, g = norm_math(ext_math(pred)), norm_math(str(gold))
        return 1.0 if p and g and p == g else 0.0
    elif ttype == "code":
        code = pred
        if "```python" in code: code = code.split("```python")[1].split("```")[0]
        elif "```" in code: code = code.split("```")[1].split("```")[0]
        return 1.0 if len(code) > 30 and bool(re.search(r'def\s+\w+', code)) else 0.5 if len(code) > 30 else 0.0
    elif ttype == "binary":
        p = str(pred).strip().upper()
        g = str(gold).strip().upper()
        if "YES" in p and "NO" not in p: p = "YES"
        elif "NO" in p and "YES" not in p: p = "NO"
        return 1.0 if p == g else 0.0
    else: return 1.0 if pred and len(pred) > 10 else 0.0

def load_bench(filename):
    path = os.path.join(BENCHMARK_DIR, filename)
    if not os.path.exists(path): return []
    cases = []
    with open(path) as f:
        for line in f:
            if not line.strip(): continue
            try:
                case = json.loads(line)
                if isinstance(case, dict): cases.append(case)
            except: pass
    return cases

def fmt_prompt(case, ttype):
    if ttype == "mcq":
        q = str(case.get("question", case.get("prompt", "")))[:2000]
        choices = case.get("choices") or case.get("options")
        if isinstance(choices, dict):
            ct = "\n".join(f"{k}. {str(v)[:200]}" for k, v in sorted(choices.items()))
        elif isinstance(choices, list):
            labels = [chr(ord('A')+i) for i in range(len(choices))]
            ct = "\n".join(f"{l}. {str(c)[:200]}" for l, c in zip(labels, choices))
        else: ct = str(choices)[:500]
        return f"{q}\n\n{ct}\n\nAnswer with only the letter."
    elif ttype == "math":
        p = str(case.get("problem", case.get("question", case.get("prompt", ""))))[:2000]
        return f"Solve. Put answer in \\boxed{{}}:\n\n{p}"
    elif ttype == "code":
        p = str(case.get("prompt", case.get("question", "")))[:2000]
        return f"Write Python code:\n\n{p}"
    elif ttype == "binary":
        q = str(case.get("question", case.get("prompt", "")))[:2000]
        return f"{q}\n\nAnswer YES or NO."
    else: return str(case.get("question", case.get("prompt", "")))[:2000]

def get_gold(case, ttype):
    if ttype == "mcq": return str(case.get("answer", case.get("label", ""))).strip().upper()
    elif ttype == "math": return str(case.get("answer", case.get("solution", "")))
    elif ttype == "binary": return str(case.get("answer", case.get("label", ""))).strip().upper()
    return str(case.get("answer", case.get("label", "")))

def run_model(model):
    results = {}
    total_s, total_c, total_lat = 0, 0, 0
    t0 = time.time()
    for filename, label, ttype in BENCHMARKS:
        cases = load_bench(filename)[:MAX_SAMPLES]
        if not cases:
            print(f"  [{label}] No cases", flush=True)
            continue
        scores, lats, errs = [], [], 0
        for case in cases:
            prompt = fmt_prompt(case, ttype)
            gold = get_gold(case, ttype)
            messages = [{"role": "user", "content": prompt}]
            max_tok = 512 if ttype in ("code", "math") else 256
            t1 = time.time()
            resp, err = call_axio(model, messages, max_tok)
            elapsed = time.time() - t1
            if resp and not err:
                scores.append(score(resp, gold, ttype))
                lats.append(elapsed)
            else:
                scores.append(0.0)
                lats.append(elapsed)
                errs += 1
        acc = sum(scores) / max(len(scores), 1)
        avg_lat = sum(lats) / max(len(lats), 1)
        results[label] = {"acc": round(acc, 3), "n": len(scores), "lat": round(avg_lat, 1), "err": errs}
        total_s += sum(scores); total_c += len(scores); total_lat += sum(lats)
        print(f"  [{label}] {sum(scores):.1f}/{len(scores)} ({acc:.0%}) {avg_lat:.1f}s err={errs}", flush=True)
    wall = time.time() - t0
    overall = {"acc": round(total_s / max(total_c, 1), 3), "correct": total_s, "total": total_c, "avg_lat": round(total_lat / max(total_c, 1), 1), "wall": round(wall, 0)}
    return results, overall

print("=" * 60, flush=True)
print(f"Axio Fusion Evaluation | {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
print(f"Benchmarks: {len(BENCHMARKS)} | Samples: {MAX_SAMPLES} | Proxy: {PROXY}", flush=True)
print("=" * 60, flush=True)

all_results = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "models": {}}

for model in MODELS:
    print(f"\n--- {model} ---", flush=True)
    bench, overall = run_model(model)
    all_results["models"][model] = {"benchmarks": bench, "overall": overall}
    print(f"  OVERALL: {overall['acc']:.0%} ({overall['correct']:.1f}/{overall['total']}) {overall['avg_lat']:.1f}s wall={overall['wall']:.0f}s", flush=True)

# Comparison
print("\n=== COMPARISON ===", flush=True)
if "axio-fast" in all_results["models"] and "axio-terra" in all_results["models"]:
    f = all_results["models"]["axio-fast"]["overall"]
    t = all_results["models"]["axio-terra"]["overall"]
    print(f"axio-fast: {f['acc']:.0%} @ {f['avg_lat']:.1f}s", flush=True)
    print(f"axio-terra: {t['acc']:.0%} @ {t['avg_lat']:.1f}s", flush=True)
    print(f"terra vs fast: delta={t['acc']-f['acc']:+.0%}", flush=True)

out = os.path.join(RESULTS_DIR, f"eval_{time.strftime('%Y%m%d_%H%M%S')}.json")
with open(out, 'w') as f: json.dump(all_results, f, indent=2)
print(f"\nSaved: {out}", flush=True)
