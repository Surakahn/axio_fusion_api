from __future__ import annotations

import os
import subprocess
import sys


def test_production_import_does_not_load_evaluation_module():
    source_root = os.path.dirname(os.path.dirname(__file__))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.path.join(source_root, "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import axio_fusion_api; "
                "import axio_fusion_api.service_cli; "
                "import axio_fusion_api.server; "
                "assert 'axio_fusion_api.evaluation' not in sys.modules"
            ),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_production_gateway_does_not_expose_benchmark_control_endpoint():
    from axio_fusion_api.server import _presented_auth_values, handle_request

    assert "gemini-secret" in _presented_auth_values(
        {"x-goog-api-key": "gemini-secret"}
    )
    status, _headers, _body = handle_request(
        method="GET",
        path="/v1/benchmarks",
        headers={},
        body=b"",
        engine=object(),
        record_trace=False,
        record_runtime=False,
    )
    assert status != 200
