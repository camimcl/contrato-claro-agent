import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path():
    # mkdir's default mode works in Windows restricted environments where
    # O modo 0o700 do tempfile impede o acesso do processo isolado aos arquivos.
    path = Path("artifacts/test-tmp") / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path.resolve()
