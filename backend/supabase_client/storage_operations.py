from typing import List, Dict, Tuple
import json
from supabase_client.supabase_init import supabase_admin

# def upload_images_and_manifest(
#     bucket: str,
#     images: List[Tuple[str, bytes]],
#     manifest: Dict,
#     manifest_remote_path: str,
#     input_prefix: str
# ) -> None:
#     """
#     images: List of (filename, bytes)
#     """
#     try:
#         for filename, content in images:
#             supabase_admin.storage.from_(bucket).upload(
#                 path=f"{input_prefix}/{filename}",
#                 file=content,
#                 file_options={"content-type": "image/png"}
#             )

#         manifest_bytes = json.dumps(manifest).encode("utf-8")
#         supabase_admin.storage.from_(bucket).upload(
#             path=manifest_remote_path,
#             file=manifest_bytes,
#             file_options={"content-type": "application/json"}
#         )

#     except Exception as e:
#         raise RuntimeError(f"[UPLOAD FAILED] {str(e)}") from e


# def delete_images_create_report(
#     bucket: str,
#     input_prefix: str,
#     report_prefix: str,
#     report_filename: str
# ) -> str:
#     try:
#         with open(report_filename, "rb") as pdf_file:
#             supabase_admin.storage.from_(bucket).upload(
#                 path=f"{report_prefix}/{report_filename}",
#                 file=pdf_file,
#                 file_options={"content-type": "application/pdf"}
#             )

#         files = supabase_admin.storage.from_(bucket).list(input_prefix)

#         delete_targets = [
#             f"{input_prefix}/{f['name']}"
#             for f in files
#         ]

#         if delete_targets:
#             supabase_admin.storage.from_(bucket).remove(delete_targets)

#         return f"{report_prefix}/{report_filename}"

#     except Exception as e:
#         raise RuntimeError(f"[DELETE FAILED] {str(e)}") from e

# def create_signed_report_url(
#     bucket: str,
#     report_path: str,
#     expiry_seconds: int = 86400
# ) -> str:
#     try:
#         response = supabase_admin.storage.from_(bucket).create_signed_url(
#             path=report_path,
#             expires_in=expiry_seconds
#         )

#         signed_url = response.get("signedURL")
#         if not signed_url:
#             raise ValueError("Signed URL not returned")

#         return signed_url

#     except Exception as e:
#         raise RuntimeError(f"[SIGNED URL FAILED] {str(e)}") from e