#!/usr/bin/env python3
"""Run one non-formal diagnostic benchmark for one baseline via CPA Plus."""
import json, os, time, re, urllib.request, sys
from pathlib import Path

if len(sys.argv) < 4:
    print("Usage: run_one_baseline.py <model> <bench_file> <bench_label> <task_type> [out_dir]")
    sys.exit(1)

model = sys.argv[1]; bench_file = sys.argv[2]; bench_label = sys.argv[3]; task_type = sys.argv[4]
out_dir = sys.argv[5] if len(sys.argv) > 5 else "data/evaluation_results"
max_samples = 10; timeout = 60

CPA_URL = os.environ.get("AXIO_CPA_PLUS_BASE_URL", "https://cpa.co6.click/v1").rstrip("/")
CPA_KEY = os.environ.get("AXIO_CPA_PLUS_API_KEY", "").strip()
BENCHMARK_DIR = "data/benchmarks"

if not CPA_KEY:
    raise SystemExit("AXIO_CPA_PLUS_API_KEY is required")

def call_provider(model, messages, max_tokens=256):
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "curl/8.0", "Authorization": f"Bearer {CPA_KEY}"}
    req = urllib.request.Request(f"{CPA_URL}/chat/completions", data=data, headers=headers)
    resp = urllib.request.urlopen(req, timeout=timeout)
    body = json.loads(resp.read().decode())
    return body["choices"][0]["message"]["content"]

def norm_ans(text):
    if not text: return ""
    text = str(text).strip().upper()
    for pat in [r'\bANSWER\s*(?:IS\s*)?[:\-]?\s*([A-J])\b', r'\b([A-J])\)', r'\b([A-J])\b']:
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
        has_def = bool(re.search(r'def\s+\w+', code))
        return 1.0 if len(code) > 30 and has_def else 0.4 if len(code) > 30 else 0.0
    elif ttype == "binary":
        p = str(pred).strip().upper(); g = str(gold).strip().upper()
        if "YES" in p and "NO" not in p: p = "YES"
        elif "NO" in p and "YES" not in p: p = "NO"
        return 1.0 if p == g else 0.0
    return 1.0 if pred and len(pred) > 10 else 0.0

# (same fmt_prompt and get_gold as run_one_bench.py)
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
    return str(case.get("question", case.get("prompt", "")))[:2000]

def get_gold(case, ttype):
    if ttype == "mcq": return str(case.get("answer", case.get("label", ""))).strip().upper()
    elif ttype == "math": return str(case.get("answer", case.get("solution", "")))
    elif ttype == "binary": return str(case.get("answer", case.get("label", ""))).strip().upper()
    return str(case.get("answer", case.get("label", "")))

path = os.path.join(BENCHMARK_DIR, bench_file)
cases = []
with open(path) as f:
    for line in f:
        if not line.strip(): continue
        try:
            case = json.loads(line)
            if isinstance(case, dict): cases.append(case)
        except: pass
        if len(cases) >= max_samples: break

print(f"[{bench_label}] {model}: {len(cases)} cases", flush=True)
scores, lats, errs = [], [], 0
for i, case in enumerate(cases):
    prompt = fmt_prompt(case, task_type)
    gold = get_gold(case, task_type)
    messages = [{"role": "user", "content": prompt}]
    max_tok = 512 if task_type in ("code", "math") else 256
    t1 = time.time()
    try:
        resp = call_provider(model, messages, max_tok)
        elapsed = time.time() - t1
        scores.append(score(resp, gold, task_type))
        lats.append(elapsed)
        print(f"  [{i+1}/{len(cases)}] {scores[-1]:.0f} ({elapsed:.1f}s)", flush=True)
    except Exception as e:
        elapsed = time.time() - t1
        scores.append(0.0); lats.append(elapsed); errs += 1
        print(f"  [{i+1}/{len(cases)}] ERR ({elapsed:.1f}s): {type(e).__name__}", flush=True)

acc = sum(scores) / max(len(scores), 1)
avg_lat = sum(lats) / max(len(lats), 1)
result = {"model": model, "benchmark": bench_label, "task_type": task_type, "accuracy": round(acc,3), "correct": sum(scores), "total": len(scores), "avg_latency_s": round(avg_lat,1), "errors": errs}
Path(out_dir).mkdir(parents=True, exist_ok=True)
out_file = os.path.join(out_dir, f"BASELINE_{model}_{bench_label.replace(' ','_')}.json")
with open(out_file, 'w') as f: json.dump(result, f, indent=2)
print(f"[{bench_label}] {model}: {sum(scores):.0f}/{len(scores)} ({acc:.0%}) {avg_lat:.1f}s | {out_file}", flush=True)
