"""Test root and subdirectory hosting without relying on a particular proxy."""

import os
from fastapi import FastAPI
from services.api.main import app as workspace, lifespan

prefix = os.environ.get("CAESAR_TEST_MOUNT", "")
if prefix:
    app = FastAPI(lifespan=lifespan)
    app.mount(prefix, workspace)
else:
    app = workspace
