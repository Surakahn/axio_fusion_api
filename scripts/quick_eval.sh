#!/bin/bash
# Quick evaluation: Axio Fusion vs Single-Model Baselines
# Tests 3 benchmarks covering Science, Math, and Logic

AXIO="http://127.0.0.1:18900"
RESULTS="/tmp/quick_eval_$(date +%H%M%S).txt"

echo "=== Axio Fusion Quick Evaluation ===" | tee "$RESULTS"
echo "Time: $(date)" | tee -a "$RESULTS"

test_mcq() {
    local model=$1 prompt=$2 answer=$3
    local resp=$(curl -s --max-time 60 --noproxy '127.0.0.1' -X POST "$AXIO/v1/chat/completions" \
        -H "Content-Type: application/json" -H "Authorization: Bearer test" \
        -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":$(echo "$prompt" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")}],\"max_tokens\":50,\"stream\":false}" 2>/dev/null)
    local text=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content',''))" 2>/dev/null)
    local letter=$(echo "$text" | grep -o '[A-E]' | head -1)
    if [ "$letter" = "$answer" ]; then echo "CORRECT"; else echo "WRONG (got $letter, expected $answer)"; fi
}

# Test 1: Science - MMLU question
echo "" | tee -a "$RESULTS"
echo "--- Science: MMLU Biology ---" | tee -a "$RESULTS"
Q="Question: Which organelle is responsible for energy production in eukaryotic cells?\nChoices: ['A. Nucleus', 'B. Mitochondria', 'C. Endoplasmic reticulum', 'D. Golgi apparatus']. Answer with the letter only."
A="B"
for model in axio-fast axio-terra axio-pro; do
    result=$(test_mcq "$model" "$Q" "$A")
    echo "  $model: $result" | tee -a "$RESULTS"
done

# Test 2: Math
echo "" | tee -a "$RESULTS"
echo "--- Math: Arithmetic ---" | tee -a "$RESULTS"
Q="Solve: If a triangle has sides of length 3, 4, and 5, what is its area?\nOutput only the number."
A="6"
for model in axio-fast axio-terra axio-pro; do
    resp=$(curl -s --max-time 60 --noproxy '127.0.0.1' -X POST "$AXIO/v1/chat/completions" \
        -H "Content-Type: application/json" -H "Authorization: Bearer test" \
        -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":$(echo "$Q" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")}],\"max_tokens\":50,\"stream\":false}" 2>/dev/null)
    text=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content',''))" 2>/dev/null)
    echo "  $model: $text" | tee -a "$RESULTS"
done

# Test 3: Logic
echo "" | tee -a "$RESULTS"
echo "--- Logic: Syllogism ---" | tee -a "$RESULTS"
Q="All dogs are animals. All animals need water. Does a dog need water? Answer yes or no."
A="yes"
for model in axio-fast axio-terra axio-pro; do
    resp=$(curl -s --max-time 60 --noproxy '127.0.0.1' -X POST "$AXIO/v1/chat/completions" \
        -H "Content-Type: application/json" -H "Authorization: Bearer test" \
        -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":$(echo "$Q" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))")}],\"max_tokens\":50,\"stream\":false}" 2>/dev/null)
    text=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content',''))" 2>/dev/null)
    echo "  $model: $text" | tee -a "$RESULTS"
done

echo "" | tee -a "$RESULTS"
echo "=== Complete ===" | tee -a "$RESULTS"
