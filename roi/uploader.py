"""S3 upload + presigned URL for shareable dashboard links."""

import time
import boto3


def upload_and_sign(
    html: str,
    slug: str,
    bucket: str,
    region: str,
    expiry_seconds: int,
) -> str:
    key = f"reports/{slug}_{int(time.time())}.html"
    s3 = boto3.client("s3", region_name=region)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiry_seconds,
    )
