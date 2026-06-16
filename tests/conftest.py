import os
import tempfile

# Configure the service for tests BEFORE app modules import settings.
_tmp = tempfile.mkdtemp(prefix="ocr-test-")
os.environ.setdefault("API_KEY", "test-key")
os.environ["DATA_DIR"] = _tmp
os.environ["DB_PATH"] = os.path.join(_tmp, "jobs.db")

# Create the schema up front. A plain TestClient(app) does not run the app's
# lifespan, so the API tests can't rely on it to build the jobs table.
from app import db  # noqa: E402  (must follow the env setup above)

db.init_db()
