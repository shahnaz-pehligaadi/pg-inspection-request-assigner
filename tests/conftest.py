import os

# Provide required env so `Settings()` can be imported in tests.
os.environ.setdefault("INSPECTION_SERVICE_URL", "http://inspection-service.test")
os.environ.setdefault("INTERNAL_API_KEY", "test-key")
