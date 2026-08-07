import os, sys, signal

os.environ['AXIO_FUSION_NETWORK_MODE'] = 'auto'
os.environ['AXIO_FUSION_SYSTEM_PROXY'] = 'http://127.0.0.1:10808'
os.environ['AXIO_FUSION_REGISTRY_PATH'] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'private/current_channel_enrollment_20260728_combined_r1/runtime_registry.calibrated.private.json'
)
# Provider channel credentials - resolved from env only, never persisted
os.environ['AXIO_NVIDIA_BASE_URL'] = 'https://integrate.api.nvidia.com/v1'
os.environ['AXIO_NVIDIA_API_KEYS'] = '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,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,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,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,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'
os.environ['AXIO_TOKENAPIS_BASE_URL'] = 'https://tokenapis.com/v1'
os.environ['AXIO_TOKENAPIS_API_KEY'] = 'sk-9023fc08bd8788b07e426144de48ac476b3de9e1e532f1fd67719b9b12e5e1ef'

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from axio_fusion_api.registry import load_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.providers import HTTPProviderClient
from axio_fusion_api.server import create_http_server

profiles = load_registry(require_prefusion=False)
print(f'Loaded {len(profiles)} profiles', file=sys.stderr, flush=True)

engine = FusionEngine(profiles, client=HTTPProviderClient(require_streaming=True))
print('Engine created', file=sys.stderr, flush=True)

server = create_http_server(
    host='127.0.0.1',
    port=18900,
    live=True,
    engine=engine,
    image_profiles=[],
)

def handle_signal(signum, frame):
    print('Shutting down...', file=sys.stderr)
    server.shutdown()
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

print('Axio Fusion API server running on http://127.0.0.1:18900', file=sys.stderr, flush=True)
server.serve_forever()
