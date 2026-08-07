#!/bin/bash
# Verify all 4 API formats for all 3 Axio models
AXIO="http://127.0.0.1:18900"
NOPROXY="--noproxy 127.0.0.1"

echo "=== API Format Verification ==="
echo "Time: $(date)"
echo ""

for model in axio-fast axio-terra axio-pro; do
    echo "--- $model ---"
    
    # Chat/Completions
    r=$(curl -s --max-time 60 $NOPROXY -X POST "$AXIO/v1/chat/completions" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in one word.\"}],\"max_tokens\":50,\"stream\":false}" 2>/dev/null)
    t=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content','?'))" 2>/dev/null)
    echo "  Chat:     $t"
    
    # Responses
    r=$(curl -s --max-time 60 $NOPROXY -X POST "$AXIO/v1/responses" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$model\",\"input\":[{\"role\":\"user\",\"content\":\"Say hello in one word.\"}],\"max_output_tokens\":50}" 2>/dev/null)
    t=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin)
for o in d.get('output',[]):
    if o.get('type')=='message':
        for c in o.get('content',[]):
            if c.get('type')=='output_text': print(c['text'])" 2>/dev/null)
    echo "  Responses: $t"
    
    # Anthropic
    r=$(curl -s --max-time 60 $NOPROXY -X POST "$AXIO/v1/messages" \
        -H "Content-Type: application/json" -H "anthropic-version: 2023-06-01" \
        -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in one word.\"}],\"max_tokens\":50}" 2>/dev/null)
    t=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin)
for c in d.get('content',[]):
    if c.get('type')=='text': print(c['text'])" 2>/dev/null)
    echo "  Anthropic: $t"
    
    # Gemini
    r=$(curl -s --max-time 60 $NOPROXY -X POST "$AXIO/v1beta/models/$model:generateContent" \
        -H "Content-Type: application/json" \
        -d "{\"contents\":[{\"role\":\"user\",\"parts\":[{\"text\":\"Say hello in one word.\"}]}],\"generationConfig\":{\"maxOutputTokens\":50}}" 2>/dev/null)
    t=$(echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin)
for c in d.get('candidates',[]):
    for p in c.get('content',{}).get('parts',[]):
        if 'text' in p: print(p['text'])" 2>/dev/null)
    echo "  Gemini:    $t"
    
    echo ""
done

echo "=== Complete ==="
