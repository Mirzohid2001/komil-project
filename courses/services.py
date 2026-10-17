"""Course-domain services kept out of views to avoid circular imports."""
import os
import uuid
from io import BytesIO

from django.conf import settings
from xhtml2pdf import pisa

from .models import CourseCertificate


def generate_course_certificate_pdf(certificate):
    """Generate and attach a simple PDF for a course certificate."""
    user = certificate.enrollment.user
    course = certificate.enrollment.course
    verification_url = f"{settings.BASE_URL}/verify-certificate/{certificate.certificate_id}"
    issue_date = certificate.issue_date.strftime('%d.%m.%Y') if certificate.issue_date else ''

    html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          body {{ font-family: DejaVu Sans, sans-serif; text-align: center; padding: 40px; }}
          h1 {{ color: #0d6efd; margin-bottom: 8px; }}
          .name {{ font-size: 28px; margin: 24px 0 8px; }}
          .course {{ font-size: 20px; margin: 8px 0 24px; }}
          .meta {{ color: #555; font-size: 12px; margin-top: 40px; }}
        </style>
      </head>
      <body>
        <h1>SERTIFIKAT</h1>
        <p>Ushbu sertifikat quyidagi shaxsga beriladi:</p>
        <div class="name">{user.get_full_name() or user.username}</div>
        <p>quyidagi kursni muvaffaqiyatli yakunlagani uchun:</p>
        <div class="course">{course.title}</div>
        <p>{certificate.title}</p>
        <div class="meta">
          <div>Sana: {issue_date}</div>
          <div>ID: {certificate.certificate_id}</div>
          <div>Tekshirish: {verification_url}</div>
        </div>
      </body>
    </html>
    """

    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode('utf-8')), result)
    if pdf.err:
        return None

    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'certificates', 'courses'), exist_ok=True)
    file_name = f"{certificate.certificate_id}.pdf"
    relative_path = os.path.join('certificates', 'courses', file_name)
    absolute_path = os.path.join(settings.MEDIA_ROOT, relative_path)
    with open(absolute_path, 'wb') as pdf_file:
        pdf_file.write(result.getvalue())

    certificate.pdf_file.name = relative_path
    certificate.save(update_fields=['pdf_file'])
    return certificate


def create_course_certificate(enrollment):
    """Create a course completion certificate (and PDF) for an enrollment."""
    existing = CourseCertificate.objects.filter(enrollment=enrollment).first()
    if existing:
        if not existing.pdf_file:
            generate_course_certificate_pdf(existing)
        return existing

    certificate = CourseCertificate.objects.create(
        enrollment=enrollment,
        certificate_id=str(uuid.uuid4()),
        title=f"{enrollment.course.title} kursi sertifikati",
        certificate_type='course',
    )
    generate_course_certificate_pdf(certificate)
    return certificate
