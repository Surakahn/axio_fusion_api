#!/bin/bash
# Master benchmark runner - one suite at a time, resume-safe
set -e
cd /home/he/axio_fusion_api
BENCHES=(
    "math_500.jsonl"
    "aime_recent.jsonl"
    "arc_challenge.jsonl"
    "truthfulqa.jsonl"
    "mmmu_text_science.jsonl"
    "medqa_usmle.jsonl"
    "global_mmlu_lite.jsonl"
    "legalbench.jsonl"
    "financebench.jsonl"
    "bizbench.jsonl"
    "policyllm_policybench.jsonl"
    "flores_translation_instruction.jsonl"
    "halueval.jsonl"
    "bbh.jsonl"
)

for bench in "${BENCHES[@]}"; do
    RESULT_FILE="/tmp/bench_single_${bench%.jsonl}.json"
    if [ -f "$RESULT_FILE" ]; then
        COMPLETED=$(python3 -c "import json; d=json.load(open('$RESULT_FILE')); print(d.get('completed',False))" 2>/dev/null || echo "False")
        if [ "$COMPLETED" = "True" ]; then
            echo "SKIP $bench - already completed"
            continue
        fi
        echo "RESUME $bench - partial progress exists"
    fi
    echo "================================================"
    echo "RUNNING: $bench"
    echo "================================================"
    PYTHONPATH=src timeout 600 .venv/bin/python -u scripts/run_single_bench.py "$bench" 10 2>&1 | tee "/tmp/bench_log_${bench%.jsonl}.log"
    echo "DONE: $bench"
done

echo "================================================"
echo "ALL BENCHMARKS COMPLETE - Aggregating results"
echo "================================================"

python3 << 'PYEOF'
import json, os
from pathlib import Path

results = {}
for f in sorted(Path('/tmp').glob('bench_single_*.json')):
    try:
        d = json.loads(open(f))
        if d.get('completed'):
            results[d['bench_file']] = d
    except: pass

print(f"Found {len(results)} completed benchmarks\n")
wins = losses = ties = 0
for bench, data in sorted(results.items()):
    print(f"--- {bench} ---")
    for m in ['axio-fast','axio-terra','axio-pro','gpt-5.6-luna','gpt-5.6-terra','gpt-5.6-sol']:
        a = data.get(f'{m}_avg', 'N/A')
        print(f"  {m:16s}: {a}")
    for ax,ba in [('axio-fast','gpt-5.6-luna'),('axio-terra','gpt-5.6-terra'),('axio-pro','gpt-5.6-sol')]:
        av = data.get(f'{ax}_avg', 0)
        bv = data.get(f'{ba}_avg', 0)
        f = 'WIN' if av>bv else ('LOSE' if av<bv else 'TIE')
        print(f"  {ax} vs {ba}: {f} ({av:.3f} vs {bv:.3f})")
        if av > bv: wins += 1
        elif av < bv: losses += 1
        else: ties += 1

total = wins + losses + ties
print(f"\n{'='*50}")
print(f"FINAL: {wins}W {losses}L {ties}T / {total}")
print(f"{'='*50}")

# Save aggregate
with open('/tmp/bench_all_results.json','w') as f:
    json.dump({'wins':wins,'losses':losses,'ties':ties,'results':{k:{kk:vv for kk,vv in v.items() if not kk.endswith('_scores')} for k,v in results.items()}}, f, indent=2)
PYEOF
