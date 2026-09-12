import base64
import os


def bytes_to_data_url(file_bytes: bytes, filename: str) -> str:
    """
    이미지 바이트 데이터를 브라우저 렌더링용 Base64 Data URL로 변환
    컨테이너 재배포 시에도 MariaDB에 영구 보존되도록 지원
    """
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "svg": "image/svg+xml"
    }
    mime = mime_map.get(ext, "image/jpeg")
    b64_str = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64_str}"
