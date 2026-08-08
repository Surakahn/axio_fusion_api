import os, sys, signal, threading

os.environ.setdefault('AXIO_FUSION_NETWORK_MODE', 'auto')
os.environ.setdefault('AXIO_FUSION_SYSTEM_PROXY', 'http://127.0.0.1:10808')
os.environ.setdefault('AXIO_NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1')
os.environ.setdefault('AXIO_CPA_PLUS_BASE_URL', 'https://cpa.co6.click/v1')

required_secrets = ('AXIO_NVIDIA_API_KEYS', 'AXIO_CPA_PLUS_API_KEY')
missing_secrets = [name for name in required_secrets if not os.environ.get(name, '').strip()]
if missing_secrets:
    raise SystemExit(
        'Missing provider credentials in the process environment: '
        + ', '.join(missing_secrets)
        + '. Source private/current_channels.env before starting the server.'
    )

registry_path = os.environ.get('AXIO_FUSION_REGISTRY_PATH', '').strip()
if not registry_path:
    raise SystemExit(
        'AXIO_FUSION_REGISTRY_PATH must point to the current '
        'pre-Fusion serving registry before starting the live server.'
    )

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from axio_fusion_api.registry import load_registry
from axio_fusion_api.registry import load_image_registry
from axio_fusion_api.orchestrator import FusionEngine
from axio_fusion_api.providers import HTTPProviderClient
from axio_fusion_api.server import create_http_server

profiles = load_registry(registry_path, require_prefusion=True)
print(f'Loaded {len(profiles)} profiles', file=sys.stderr, flush=True)

engine = FusionEngine(profiles, client=HTTPProviderClient(require_streaming=True))
print('Engine created', file=sys.stderr, flush=True)

image_registry_path = os.environ.get('AXIO_FUSION_IMAGE_REGISTRY_PATH', '').strip()
image_profiles = load_image_registry(image_registry_path) if image_registry_path else []
server = create_http_server(
    host='127.0.0.1',
    port=18900,
    live=True,
    engine=engine,
    image_profiles=image_profiles,
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
signal.signal(signal.SIGHUP, handle_signal)

print('Axio Fusion API server running on http://127.0.0.1:18900', file=sys.stderr, flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
