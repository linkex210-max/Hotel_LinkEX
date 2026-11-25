from pathlib import Path
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError

MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}


def _validate_size(file_obj, max_bytes: int = MAX_UPLOAD_SIZE_BYTES) -> None:
    if file_obj.size > max_bytes:
        raise ValidationError(_("حجم الملف يتجاوز الحد الأقصى المسموح به (5 ميجابايت)."))


def _verify_image_content(file_obj) -> None:
    pos = file_obj.tell()
    try:
        img = Image.open(file_obj)
        img.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValidationError(_("محتوى الصورة غير صالح أو تالف."))
    finally:
        file_obj.seek(pos)


def _verify_pdf_content(file_obj) -> None:
    pos = file_obj.tell()
    try:
        header = file_obj.read(5)
        if header != b'%PDF-':
            raise ValidationError(_("محتوى ملف PDF غير صالح."))
    finally:
        file_obj.seek(pos)


def validate_image_upload(file_obj) -> None:
    """التحقق من امتداد وحجم ومحتوى الصور المرفوعة."""
    _validate_size(file_obj)
    ext = Path(file_obj.name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError(_("امتداد الصورة غير مدعوم. المسموح: JPG, JPEG, PNG, WEBP."))
    _verify_image_content(file_obj)


def validate_document_or_image_upload(file_obj) -> None:
    """التحقق من امتداد وحجم ومحتوى الفواتير والمستندات المرفوعة (PDF أو صورة)."""
    _validate_size(file_obj)
    ext = Path(file_obj.name).suffix.lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError(_("نوع الملف غير مدعوم. المسموح: PDF, JPG, JPEG, PNG."))
    if ext == '.pdf':
        _verify_pdf_content(file_obj)
    else:
        _verify_image_content(file_obj)
