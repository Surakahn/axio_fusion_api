import os, sys, signal, threading

os.environ.setdefault('AXIO_FUSION_NETWORK_MODE', 'auto')
os.environ.setdefault('AXIO_FUSION_SYSTEM_PROXY', 'http://127.0.0.1:10808')
os.environ.setdefault('AXIO_FUSION_REGISTRY_PATH', os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'private/current_channel_enrollment_20260728_combined_r1/runtime_registry.calibrated.private.json'
))
os.environ.setdefault('AXIO_NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1')
os.environ.setdefault('AXIO_TOKENAPIS_BASE_URL', 'https://tokenapis.com/v1')

required_secrets = ('AXIO_NVIDIA_API_KEYS', 'AXIO_TOKENAPIS_API_KEY')
missing_secrets = [name for name in required_secrets if not os.environ.get(name, '').strip()]
if missing_secrets:
    raise SystemExit(
        'Missing provider credentials in the process environment: '
        + ', '.join(missing_secrets)
        + '. Source private/current_channels.env before starting the server.'
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

shutdown_started = False


def handle_signal(signum, frame):
    global shutdown_started
    if shutdown_started:
        return
    shutdown_started = True
    print('Shutting down...', file=sys.stderr, flush=True)
    # BaseServer.shutdown() waits for serve_forever() to exit and therefore
    # must not run in the signal handler on the serving thread.
    threading.Thread(target=server.shutdown, daemon=True).start()

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

print('Axio Fusion API server running on http://127.0.0.1:18900', file=sys.stderr, flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
