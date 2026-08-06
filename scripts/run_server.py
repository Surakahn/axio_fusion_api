import os, sys, signal

os.environ['AXIO_FUSION_NETWORK_MODE'] = 'auto'
os.environ['AXIO_FUSION_SYSTEM_PROXY'] = 'http://127.0.0.1:10808'
os.environ['AXIO_FUSION_REGISTRY_PATH'] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'private/current_channel_enrollment_20260728_combined_r1/runtime_registry.calibrated.private.json'
)

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
