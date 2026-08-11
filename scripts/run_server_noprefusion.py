#!/usr/bin/env python3.11
"""Run the Axio Fusion API server without pre-fusion validation (mixed registry)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from axio_fusion_api.registry import load_registry
from axio_fusion_api.server import serve

registry_path = os.environ.get('AXIO_FUSION_REGISTRY_PATH', '').strip()
if not registry_path:
    print("FATAL: AXIO_FUSION_REGISTRY_PATH must be set")
    sys.exit(1)

profiles = load_registry(registry_path, require_prefusion=False)
print(f"Loaded {len(profiles)} profiles from registry")

serve(host='127.0.0.1', port=18900, live=True, require_prefusion=False)
