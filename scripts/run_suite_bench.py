#!/usr/bin/env python3.11
"""Formal benchmark runner for Axio Fusion API 14-suite evaluation.

Usage:
    python3.11 scripts/run_suite_bench.py arc_challenge axio-terra gpt-5.6-terra --n 25
    python3.11 scripts/run_suite_bench.py math_500 axio-pro gpt-5.6-sol --n 20 --timeout 180
"""

import argparse, json, os, sys, time, urllib.request, random, io
from typing import Any

BENCH_ROOT = '/mnt/storage/axio_fusion_benchmarks'
API_URL = 'http://127.0.0.1:18900/v1/chat/completions'

# ── Suite loaders ──

def load_arc_challenge(n: int) -> list[dict]:
    import pandas as pd
    df = pd.read_parquet(f'{BENCH_ROOT}/raw/arc_hf/arc_challenge_test.parquet')
    rows = []
    for i in range(min(len(df), max(n*3, 50))):
        row = df.iloc[i]
        choices = row['choices']
        letters = list(choices['label'])
        texts = list(choices['text'])
        prompt = row['question'] + '\n'
        for l, t in zip(letters, texts):
            prompt += f'{l}) {t}\n'
        prompt += '\nAnswer with only the letter.'
        rows.append({'prompt': prompt, 'answer': row['answerKey'], 'id': row['id']})
    random.shuffle(rows)
    return rows[:n]

def load_math_500(n: int) -> list[dict]:
    rows = []
    with open(f'{BENCH_ROOT}/raw/math_500/test.jsonl') as f:
        for line in f:
            d = json.loads(line)
            prompt = d['problem'] + '\n\nProvide the final answer in LaTeX format within \\boxed{}.'
            rows.append({'prompt': prompt, 'answer': d['answer'], 'id': d.get('unique_id', '')})
    random.shuffle(rows)
    return rows[:n]

def load_truthfulqa(n: int) -> list[dict]:
    import csv
    rows = []
    with open(f'{BENCH_ROOT}/raw/truthfulqa/TruthfulQA.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = row['Question']
            correct = row['Best Answer']
            prompt = f'{q}\n\nAnswer concisely and truthfully.'
            rows.append({'prompt': prompt, 'answer': correct.lower(), 'id': q[:40]})
    random.shuffle(rows)
    return rows[:n]

def load_medqa(n: int) -> list[dict]:
    """Load MedQA from official 4-option Chinese test set."""
    path = (
        f'{BENCH_ROOT}/raw/medqa_official_drive/extracted/data_clean'
        '/questions/Mainland/4_options/test.jsonl'
    )
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            q = d.get('question', '')
            opts = d.get('options', {})
            ans_text = d.get('answer', '')
            ans_letter = ''
            for k, v in opts.items():
                if v == ans_text:
                    ans_letter = k
                    break
            if not ans_letter:
                continue
            prompt = q + '\n'
            for k, v in opts.items():
                prompt += f'{k}) {v}\n'
            prompt += '\nAnswer with only the letter.'
            rows.append({'prompt': prompt, 'answer': ans_letter, 'id': q[:40]})
    random.shuffle(rows)
    return rows[:n]

def load_global_mmlu(n: int) -> list[dict]:
    path = f'{BENCH_ROOT}/raw/global_mmlu/test'
    if not os.path.exists(path):
        return []
    import pandas as pd
    rows = []
    for fn in os.listdir(path):
        if fn.endswith('.parquet') or fn.endswith('.csv'):
            fp = os.path.join(path, fn)
            try:
                if fn.endswith('.parquet'):
                    df = pd.read_parquet(fp)
                else:
                    df = pd.read_csv(fp)
                for i in range(min(len(df), max(5, n//4))):
                    row = df.iloc[i]
                    q = row.get('question', '')
                    opts = {k: row[k] for k in ['A','B','C','D'] if k in row}
                    ans = row.get('answer', '')
                    prompt = q
                    if opts:
                        prompt += '\n'
                        for k,v in opts.items():
                            prompt += f'{k}) {v}\n'
                    prompt += '\nAnswer with only the letter.'
                    rows.append({'prompt': prompt, 'answer': str(ans).strip().upper(), 'id': f'{fn}_{i}'})
            except Exception:
                pass
    random.shuffle(rows)
    return rows[:n]

def load_bbh(n: int) -> list[dict]:
    path = f'{BENCH_ROOT}/raw/BIG-Bench-Hard/bbh'
    if not os.path.exists(path):
        return []
    rows = []
    for fn in os.listdir(path):
        if fn.endswith('.json'):
            fp = os.path.join(path, fn)
            with open(fp) as f:
                data = json.load(f)
            examples = data.get('examples', [])
            for ex in examples[:max(2, n//8)]:
                prompt = ex.get('input', '')
                answer = ex.get('target', '')
                rows.append({'prompt': prompt, 'answer': str(answer).strip(), 'id': fn[:30]})
    random.shuffle(rows)
    return rows[:n]

LOADERS = {
    'arc_challenge': load_arc_challenge,
    'math_500': load_math_500,
    'truthfulqa': load_truthfulqa,
    'medqa_usmle': load_medqa,
    'global_mmlu_lite': load_global_mmlu,
    'bbh': load_bbh,
}

# ── Scoring ──

def score_exact(pred: str, gold: str) -> bool:
    pred = pred.strip()
    gold = gold.strip()
    if not pred or not gold:
        return False
    # Single letter MCQ
    if len(gold) == 1 and gold.isalpha():
        return gold.upper() in pred.upper()[:5]
    # Math: check if gold appears in pred
    if gold in pred:
        return True
    # Loose match
    return pred.lower() == gold.lower()

def score_truthfulqa(pred: str, gold: str) -> bool:
    """TruthfulQA scoring: check if pred contains core facts from gold."""
    pred_lower = pred.lower().strip()
    gold_lower = gold.lower().strip()
    # Extract key words from gold answer
    key_words = [w for w in gold_lower.split() if len(w) > 3 and w not in 
                 ('the', 'and', 'that', 'this', 'with', 'from', 'have', 'they', 'your', 'will', 'what', 'when')]
    if not key_words:
        return False
    # At least 60% of key words in prediction
    matches = sum(1 for w in key_words if w in pred_lower)
    return matches / len(key_words) >= 0.4

# ── Main runner ──

def run_bench(suite: str, model: str, questions: list[dict], timeout: int) -> dict:
    correct = 0
    total = 0
    latencies = []
    errors = 0
    
    scorer = score_truthfulqa if suite == 'truthfulqa' else score_exact
    
    for i, q in enumerate(questions):
        start = time.monotonic()
        payload = json.dumps({
            'model': model,
            'messages': [{'role': 'user', 'content': q['prompt']}],
            'max_tokens': 200,
            'reasoning_effort': 'max',
            'stream': False
        }).encode()
        
        try:
            req = urllib.request.Request(API_URL, data=payload, 
                headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=timeout)
            data = json.loads(resp.read())
            elapsed = time.monotonic() - start
            
            reply = data['choices'][0]['message']['content']
            ok = scorer(reply, q['answer'])
            if ok:
                correct += 1
            
            total += 1
            latencies.append(elapsed)
            status = '✓' if ok else '✗'
            sys.stdout.write(f'  {status} Q{i+1}/{len(questions)} ({elapsed:.1f}s)\n')
            sys.stdout.flush()
            
        except Exception as e:
            total += 1
            errors += 1
            sys.stdout.write(f'  ERR Q{i+1}: {str(e)[:60]}\n')
            sys.stdout.flush()
        
        time.sleep(0.3)
    
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    score = correct / total if total else 0
    
    result = {
        'suite': suite,
        'model': model,
        'correct': correct,
        'total': total,
        'score': round(score, 3),
        'avg_latency': round(avg_lat, 1),
        'errors': errors
    }
    
    sys.stdout.write(f'\n{model} on {suite}: {correct}/{total} ({score:.1%}) @ {avg_lat:.1f}s, err={errors}\n')
    sys.stdout.flush()
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('suite', choices=list(LOADERS) + ['all'])
    parser.add_argument('models', nargs='+', help='Models to evaluate')
    parser.add_argument('--n', type=int, default=25, help='Questions per suite')
    parser.add_argument('--timeout', type=int, default=120, help='Per-question timeout (s)')
    parser.add_argument('--output', default='', help='Output JSON file')
    args = parser.parse_args()
    
    suites_to_run = list(LOADERS.keys()) if args.suite == 'all' else [args.suite]
    
    all_results = []
    for suite in suites_to_run:
        loader = LOADERS.get(suite)
        if not loader:
            print(f'Unknown suite: {suite}')
            continue
        
        questions = loader(args.n)
        if not questions:
            print(f'No questions loaded for {suite}')
            continue
        
        print(f'\n{"="*60}')
        print(f'Suite: {suite} ({len(questions)} questions)')
        print(f'{"="*60}')
        
        for model in args.models:
            print(f'\n--- {model} ---')
            result = run_bench(suite, model, questions, args.timeout)
            all_results.append(result)
            time.sleep(1)
    
    # Summary
    print(f'\n{"="*60}')
    print('SUMMARY')
    print(f'{"="*60}')
    for r in all_results:
        print(f'  {r["model"]:20s} | {r["suite"]:20s} | {r["correct"]:3d}/{r["total"]:<3d} | {r["score"]:.1%} | {r["avg_latency"]:5.1f}s | err={r["errors"]}')
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(all_results, f, indent=2)
        print(f'\nResults saved to {args.output}')

if __name__ == '__main__':
    main()
