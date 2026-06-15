import os
import tempfile

# Configure the service for tests BEFORE app modules import settings.
_tmp = tempfile.mkdtemp(prefix="ocr-test-")
os.environ.setdefault("API_KEY", "test-key")
os.environ["DATA_DIR"] = _tmp
os.environ["DB_PATH"] = os.path.join(_tmp, "jobs.db")
