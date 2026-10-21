"""Run the API with Uvicorn.

From the repository root, after the database migration:

    .\\.venv\\Scripts\\python.exe -m ai_governance.api
"""

import uvicorn

from ai_governance.api.app import create_app
from ai_governance.config import get_settings


def main() -> None:
    """Serve the API on the local machine."""
    settings = get_settings()
    uvicorn.run(
        create_app(settings.database_url),
        host="127.0.0.1",
        port=8000,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
