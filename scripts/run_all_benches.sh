#!/bin/bash
# Run all benchmarks for all models
cd /home/he/axio_fusion_api
export http_proxy='' https_proxy=''
OUTDIR="data/evaluation_results"
mkdir -p "$OUTDIR"

BENCHES=(
  "math_500.jsonl:Math-MATH500:math"
  "aime_recent.jsonl:Math-AIME:math"
  "humaneval.jsonl:Code-HumanEval:code"
  "arc_challenge.jsonl:Logic-ARC:mcq"
  "bbh.jsonl:Logic-BBH:mcq"
  "truthfulqa.jsonl:Hallucination-TruthfulQA:mcq"
  "halueval.jsonl:Hallucination-HaluEval:binary"
  "ifeval.jsonl:DailyWork-IFEval:instr"
  "global_mmlu_lite.jsonl:Multilingual-GlobalMMLU:mcq"
  "mmmu_text_science.jsonl:Science-MMMU-Pro:mcq"
  "medqa_usmle.jsonl:Vertical-MedQA:mcq"
  "finqa.jsonl:Vertical-FinQA:math"
  "legalbench.jsonl:Vertical-LegalBench:mcq"
)

MODELS=("axio-fast" "axio-terra")

for MODEL in "${MODELS[@]}"; do
  echo "=== $MODEL ==="
  for B in "${BENCHES[@]}"; do
    IFS=':' read -r FILE LABEL TTYPE <<< "$B"
    OUTFILE="$OUTDIR/${MODEL}_${LABEL// /_}.json"
    if [ -f "$OUTFILE" ]; then
      echo "  SKIP $LABEL (already done)"
      continue
    fi
    echo "  RUN  $LABEL ..."
    .venv/bin/python -u scripts/run_one_bench.py "$MODEL" "$FILE" "$LABEL" "$TTYPE" "$OUTDIR" 2>&1
  done
done

echo "=== ALL DONE ==="
echo "Aggregating results..."
.venv/bin/python3 -u -c "
import json, os, glob
outdir = 'data/evaluation_results'
models = {}
for f in sorted(glob.glob(f'{outdir}/axio-*.json')):
    d = json.load(open(f))
    m = d['model']
    if m not in models: models[m] = {'benchmarks': {}, 'total_correct': 0, 'total_cases': 0, 'total_latency': 0}
    models[m]['benchmarks'][d['benchmark']] = {'acc': d['accuracy'], 'n': d['total'], 'lat': d['avg_latency_s']}
    models[m]['total_correct'] += d['correct']
    models[m]['total_cases'] += d['total']
    models[m]['total_latency'] += d['avg_latency_s'] * d['total']

print()
print('='*60)
print('AXIO FUSION EVALUATION RESULTS')
print('='*60)
for m, data in sorted(models.items()):
    total_acc = data['total_correct'] / max(data['total_cases'], 1)
    avg_lat = data['total_latency'] / max(data['total_cases'], 1)
    print(f'\n{m}: {total_acc:.0%} ({data[\"total_correct\"]:.0f}/{data[\"total_cases\"]}) avg={avg_lat:.1f}s')
    for b, r in sorted(data['benchmarks'].items()):
        print(f'  {b}: {r[\"acc\"]:.0%} ({r[\"n\"]} cases, {r[\"lat\"]:.1f}s)')

summary = {m: {'acc': data['total_correct']/max(data['total_cases'],1), 'correct': data['total_correct'], 'total': data['total_cases'], 'avg_lat': data['total_latency']/max(data['total_cases'],1)} for m, data in models.items()}
with open(f'{outdir}/summary.json', 'w') as f: json.dump(summary, f, indent=2)
print(f'\nSummary saved to {outdir}/summary.json')
"
