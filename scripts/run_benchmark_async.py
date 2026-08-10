#!/usr/bin/env python3
"""Axio Fusion Benchmark Async — httpx + asyncio, true concurrent, 14 suites."""
import os, sys, json, time, random, re, asyncio
from pathlib import Path
from collections import defaultdict
import httpx

BENCH_DIR = Path('/mnt/storage/axio_fusion_benchmarks/standardized')
OUTPUT = Path('/home/he/axio_fusion_api/private/bench_results_async.json')
SAMPLES = 8
TIMEOUT = 90
MAX_CONCURRENT = 20

AXIO_URL = 'http://127.0.0.1:18900/v1/chat/completions'
CPA_URL = 'http://127.0.0.1:8317/v1/responses'
CPA_KEY = 'sk-S9APc6QARCPCC4AeM'

AXIO_MODELS = ['axio-fast', 'axio-terra', 'axio-pro']
BASELINE_MODELS = ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6-sol']

SUITES = {
    'mmmu_text_science': {'cat': 'science', 'fmt': 'mcq', 'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'global_mmlu_lite': {'cat': 'multilingual', 'fmt': 'mcq', 'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'flores_translation_instruction': {'cat': 'multilingual', 'fmt': 'open', 'qk': 'prompt', 'ak': 'answer'},
    'math_500': {'cat': 'math', 'fmt': 'math', 'qk': 'prompt', 'ak': 'answer'},
    'aime_recent': {'cat': 'math', 'fmt': 'math', 'qk': 'prompt', 'ak': 'answer'},
    'arc_challenge': {'cat': 'logic', 'fmt': 'mcq', 'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'bbh': {'cat': 'logic', 'fmt': 'open', 'qk': 'prompt', 'ak': 'answer'},
    'truthfulqa': {'cat': 'hallucination', 'fmt': 'mcq', 'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'halueval': {'cat': 'hallucination', 'fmt': 'open', 'qk': 'prompt', 'ak': 'answer'},
    'medqa_usmle': {'cat': 'vertical', 'fmt': 'mcq', 'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'legalbench': {'cat': 'vertical', 'fmt': 'mcq', 'qk': 'question', 'ok': 'options', 'ak': 'answer'},
    'bizbench': {'cat': 'vertical', 'fmt': 'open', 'qk': 'prompt', 'ak': 'answer'},
    'financebench': {'cat': 'vertical', 'fmt': 'open', 'qk': 'prompt', 'ak': 'answer'},
    'policyllm_policybench': {'cat': 'vertical', 'fmt': 'mcq', 'qk': 'question', 'ok': 'options', 'ak': 'answer'},
}

# ── Scoring ──
def extract_math_answer(text):
    t = str(text).strip()
    m = re.findall(r'\\boxed\{([^}]+)\}', t)
    if m: return m[-1].strip()
    m = re.findall(r'(?:answer|Answer)[^:]*[:=]\s*([^\n.,;]+)', t)
    if m: return m[-1].strip()
    nums = re.findall(r'-?\d+(?:\.\d+)?', t)
    if nums: return nums[-1]
    return t

def norm_math(s):
    return str(s).strip().replace(',','').replace('$','').replace('%','').replace(' ','').lower()

def score_math(pred, gold):
    p=extract_math_answer(pred); g=str(gold).strip()
    pn,gn=norm_math(p),norm_math(g)
    if pn==gn: return 1.0
    try:
        if abs(float(pn)-float(gn))<1e-4: return 1.0
        if float(gn)!=0 and abs(float(pn)-float(gn))/abs(float(gn))<1e-4: return 1.0
    except: pass
    return 0.0

def score_mcq(pred, gold):
    p=str(pred).strip().upper()[:5]; g=str(gold).strip().upper()
    for ch in p:
        if ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ': return 1.0 if ch==g else 0.0
    if g.lower() in str(pred).lower()[:50]: return 1.0
    return 0.0

def score_open(pred, gold):
    p=str(pred).strip().lower(); g=str(gold).strip().lower()
    if p==g: return 1.0
    if len(g)<=5 and g in p.split(): return 1.0
    if len(g)>5 and g in p: return 0.5
    return 0.0

SCORERS={"mcq":score_mcq,"open":score_open,"math":score_math}

def score(pred, gold, fmt):
    return SCORERS.get(fmt,score_open)(pred,gold)

# ── Data ──
def load_suite(name):
    path=BENCH_DIR/f'{name}.jsonl'
    if not path.exists(): return []
    return [json.loads(l) for l in open(path) if l.strip()]

def build_prompt(case, meta):
    q=str(case.get(meta['qk'],''))
    if meta['fmt']=='mcq':
        opts=case.get(meta.get('ok','options'),{})
        if isinstance(opts,str): return f'{q}\n\n{opts}\n\nAnswer with just the option letter.'
        olines=[f'{k}: {v}' for k,v in sorted(opts.items())] if isinstance(opts,dict) else [str(opts)]
        return f'{q}\n\nOptions:\n'+'\n'.join(olines)+'\n\nAnswer with just the option letter.'
    return q

# ── Async HTTP ──
async def call_axio(client, model, prompt):
    try:
        resp=await client.post(AXIO_URL, json={'model':model,'messages':[{'role':'user','content':prompt}],
            'max_tokens':512,'stream':False}, timeout=TIMEOUT)
        if resp.status_code==200:
            return resp.json().get('choices',[{}])[0].get('message',{}).get('content','')
        return None
    except Exception:
        return None

async def call_cpa(client, model, prompt):
    try:
        resp=await client.post(CPA_URL, json={'model':model,'input':prompt,'max_output_tokens':512,
            'reasoning':{'effort':'max'}},
            headers={'Authorization':f'Bearer {CPA_KEY}'}, timeout=TIMEOUT)
        if resp.status_code==200:
            data=resp.json()
            for item in data.get('output',[]):
                if item.get('type')=='message':
                    for c in item.get('content',[]):
                        if c.get('type')=='output_text':
                            return c['text']
            return json.dumps(data)[:500]
        return None
    except Exception:
        return None

async def run_model_tasks(model, prompts, meta):
    """Run all questions for one model concurrently."""
    sem=asyncio.Semaphore(MAX_CONCURRENT)
    async def run_one(idx, prompt, gold):
        async with sem:
            async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT)) as client:
                if model.startswith('gpt-'):
                    pred=await call_cpa(client, model, prompt)
                else:
                    pred=await call_axio(client, model, prompt)
            return idx, prompt, gold, pred
    
    tasks=[run_one(i,p,g) for i,p,g in prompts]
    results=await asyncio.gather(*tasks)
    
    correct=0.0; errors=0
    for idx,prompt,gold,pred in results:
        if pred is None:
            errors+=1
            print(f'  [{idx+1}/{len(prompts)}] ERR', flush=True)
        else:
            s=score(pred,gold,meta['fmt'])
            correct+=s
            sym='✓' if s>=1.0 else ('~' if s>=0.5 else '✗')
            ps=str(pred)[:55].replace('\n',' ').strip()
            gs=str(gold)[:35].replace('\n',' ').strip()
            print(f'  [{idx+1}/{len(prompts)}] {sym} p={ps} | g={gs}', flush=True)
    return correct, errors

# ── Main ──
async def main_async():
    os.environ['no_proxy']='127.0.0.1,localhost'
    
    if OUTPUT.exists():
        with open(OUTPUT) as f: results=json.load(f)
    else:
        results={'runs':[],'meta':{'samples':SAMPLES}}
    done={(r['suite'],r['model']) for r in results['runs']}
    
    total=sum(1 for s in SUITES if load_suite(s))*6
    print(f'=== AXIO BENCHMARK ASYNC ===')
    print(f'Suites: {len(SUITES)} Models: 6 Samples: {SAMPLES} Timeout: {TIMEOUT}s Concurrent: {MAX_CONCURRENT}')
    print(f'Done: {len(done)} Total: ~{total}')
    
    for sname, meta in SUITES.items():
        cases=load_suite(sname)
        if not cases: continue
        sampled=random.sample(cases,min(SAMPLES,len(cases)))
        
        for model in AXIO_MODELS+BASELINE_MODELS:
            if (sname,model) in done: continue
            
            prompts=[(i,build_prompt(case,meta),str(case.get(meta['ak'],''))) for i,case in enumerate(sampled)]
            meta_cat = meta["cat"]
            print(f'\n[{sname}] {model} ({meta_cat}, {len(prompts)} cases)', flush=True)
            
            t0=time.time()
            correct,errors=await run_model_tasks(model,prompts,meta)
            acc=correct/len(prompts)
            elapsed=time.time()-t0
            print(f'  → Acc: {acc:.1%} ({correct:.1f}/{len(prompts)}) {elapsed:.0f}s e{errors}', flush=True)
            
            results['runs'].append({'suite':sname,'model':model,'accuracy':acc,
                'correct':correct,'samples':len(prompts),'errors':errors,
                'elapsed_s':round(elapsed,1),'time':time.strftime('%Y-%m-%d %H:%M:%S')})
            with open(OUTPUT,'w') as f:
                json.dump(results,f,indent=2,ensure_ascii=False)
    
    # Summary
    print('\n'+'='*80+'\nFINAL RESULTS')
    ms=defaultdict(lambda:defaultdict(list))
    for r in results['runs']:
        ms[r['model']][SUITES.get(r['suite'],{}).get('cat','?')].append(r['accuracy'])
    cats=sorted(set(c for m in ms.values() for c in m))
    hdr=f'{"Model":20s} {"Overall":>8s}'+''.join(f' {c:>14s}' for c in cats)
    print(hdr+'\n'+'-'*len(hdr))
    for m in AXIO_MODELS+BASELINE_MODELS:
        cs=ms.get(m,{}); alls=[s for ss in cs.values() for s in ss]
        ov=sum(alls)/len(alls) if alls else 0
        row=f'{m:20s} {ov:7.1%}'
        for c in cats:
            vals=cs.get(c,[])
            row+=f' {sum(vals)/len(vals):13.1%}' if vals else f' {"N/A":>13s}'
        print(row)
    
    print('\n── Fusion vs Baseline ──')
    for am,bm in [('axio-pro','gpt-5.6-sol'),('axio-terra','gpt-5.6-terra'),('axio-fast','gpt-5.6-luna')]:
        as_=[r['accuracy'] for r in results['runs'] if r['model']==am]
        bs_=[r['accuracy'] for r in results['runs'] if r['model']==bm]
        if as_ and bs_:
            aa,bb=sum(as_)/len(as_),sum(bs_)/len(bs_)
            delta=aa-bb
            sym='▲' if delta>0 else ('▼' if delta<0 else '=')
            print(f'{am} vs {bm}: {sym} {delta:+.1%} ({aa:.1%} vs {bb:.1%})')
    
    print(f'\n→ {OUTPUT}')

if __name__=='__main__':
    asyncio.run(main_async())
