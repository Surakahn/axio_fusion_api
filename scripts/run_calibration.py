#!/usr/bin/env python3
"""Axio Fusion 定期校准运行器 - 25题核心能力检测

使用权重加权的28题校准集评估axio-fast/terra/pro的当前能力水平。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:18900"
TIMEOUT_S = 120
CALIBRATION_MANIFEST = Path(__file__).resolve().parent.parent / "config" / "calibration_25_tasks.json"


def load_tasks():
    with open(CALIBRATION_MANIFEST) as f:
        return json.load(f)["tasks"]


def query_model(model: str, question: str, stream: bool = False) -> str:
    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": question}],
            "max_tokens": 2048,
            "stream": stream,
        },
        timeout=TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def score_answer(model_answer: str, expected: str, suite: str) -> float:
    """简单评分: 包含正确答案关键词即得分"""
    model_lower = model_answer.lower().strip()
    expected_lower = expected.lower().strip()
    
    # 精确匹配
    if model_lower == expected_lower:
        return 1.0
    # 包含匹配
    if expected_lower and len(expected_lower) > 3 and expected_lower in model_lower:
        return 1.0
    # 选项匹配 (A/B/C/D)
    if expected_lower in ("a", "b", "c", "d") and model_lower.startswith(expected_lower):
        return 1.0
    return 0.0


def run_calibration(model: str):
    tasks = load_tasks()
    results = []
    total_weighted = 0.0
    total_weight = 0.0
    
    for task in tasks:
        try:
            answer = query_model(model, task["question"])
            score = score_answer(answer, task["answer"], task["suite"])
        except Exception as e:
            answer = f"ERROR: {e}"
            score = 0.0
        
        weighted = score * task["weight"]
        total_weighted += weighted
        total_weight += task["weight"]
        
        results.append({
            "task_id": task["task_id"],
            "suite": task["suite"],
            "score": score,
            "weight": task["weight"],
            "weighted_score": round(weighted, 2),
        })
    
    overall = round(total_weighted / total_weight * 100, 1) if total_weight > 0 else 0.0
    
    return {
        "model": model,
        "overall_weighted_score": overall,
        "tasks_completed": len(results),
        "total_tasks": len(tasks),
        "details": results,
    }


def main():
    models = ["axio-fast", "axio-terra", "axio-pro"]
    all_results = {}
    
    for model in models:
        print(f"Running calibration for {model}...", flush=True)
        result = run_calibration(model)
        all_results[model] = result
        print(f"  {model}: {result['overall_weighted_score']}% weighted score", flush=True)
        time.sleep(2)
    
    output = {
        "schema": "axio_fusion_api.calibration_result.v1",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": all_results,
    }
    
    out_path = Path("private/calibration_result.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to {out_path}")
    for model, result in all_results.items():
        print(f"{model}: {result['overall_weighted_score']}%")


if __name__ == "__main__":
    main()
