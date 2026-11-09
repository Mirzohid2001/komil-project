import re

from django.db import migrations


_AI_TITLE_RE = re.compile(r'^AI\s*test\s*:\s*', re.IGNORECASE)
_AI_PHRASE_RE = re.compile(
    r'\s*Manba:\s*ai[^\s.]*\.?',
    re.IGNORECASE,
)
_AI_DESC_MARKERS = (
    'Avtomatik (AI) yaratilgan test',
    'avtomatik (AI) yaratilgan test',
    'Rol bo‘yicha avtomatik yaratilgan test',
    'Rol bo\'yicha avtomatik yaratilgan test',
)


def scrub_ai_labels(apps, schema_editor):
    Test = apps.get_model('blog', 'Test')
    for test in Test.objects.all().iterator():
        title = test.title or ''
        description = test.description or ''
        new_title = _AI_TITLE_RE.sub('Kasbiy test: ', title)
        new_desc = _AI_PHRASE_RE.sub('', description).strip()
        for marker in _AI_DESC_MARKERS:
            if marker in new_desc:
                # Oddiy kasbiy tavsifga almashtirish
                role = getattr(test, 'role', '') or ''
                new_desc = f"{role} uchun bilimlarni tekshirish testi.".strip()
                break
        # Qolgan ochiq AI so‘zlarini yumshatish
        if 'AI' in new_title or 'Groq' in new_title or 'Gemini' in new_title:
            new_title = (
                new_title
                .replace('AI test', 'Kasbiy test')
                .replace('AI Test', 'Kasbiy test')
                .replace(' (AI)', '')
                .replace('Groq', '')
                .replace('Gemini', '')
            )
        if any(x in new_desc for x in ('AI', 'Groq', 'Gemini', 'Manba:')):
            new_desc = (
                new_desc
                .replace('Avtomatik (AI) yaratilgan test.', '')
                .replace('(AI)', '')
                .replace('Groq', '')
                .replace('Gemini', '')
            )
            new_desc = _AI_PHRASE_RE.sub('', new_desc).strip()
            new_desc = re.sub(r'\s{2,}', ' ', new_desc).strip(' .')
            if not new_desc:
                new_desc = 'Bilimlarni tekshirish testi.'

        if new_title != title or new_desc != description:
            test.title = new_title.strip()
            test.description = new_desc
            test.save(update_fields=['title', 'description'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0013_test_and_question_types'),
    ]

    operations = [
        migrations.RunPython(scrub_ai_labels, noop_reverse),
    ]
