import os

DEFAULT_REGION   = "ap-south-1"
DEFAULT_MODEL_ID = "zai.glm-5"

GA4_MEASUREMENT_ID = os.getenv("GA4_MEASUREMENT_ID", "")
TRACKING_PIXEL_URL = os.getenv("TRACKING_PIXEL_URL", "")

FLOWACE_API_TOKEN  = os.getenv("FLOWACE_API_TOKEN",  "")
FLOWACE_API_URL    = os.getenv("FLOWACE_API_URL",    "https://api.flowace.in/prod")

S3_BUCKET = os.getenv("S3_BUCKET", "")
