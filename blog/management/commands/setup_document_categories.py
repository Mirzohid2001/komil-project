from django.core.management.base import BaseCommand
from blog.models import DocumentCategory

class Command(BaseCommand):
    help = 'Set up initial document categories'

    def handle(self, *args, **options):
        categories = [
            {
                'name': 'Xujjatlar',
                'description': 'Umumiy xujjatlar va ma\'lumotlar',
                'icon': 'fas fa-file-alt'
            },
            {
                'name': 'Dasturlar',
                'description': 'Dasturiy ta\'minot va kodlar',
                'icon': 'fas fa-code'
            },
            {
                'name': 'Rasmlar',
                'description': 'Rasm va grafik fayllar',
                'icon': 'fas fa-image'
            },
            {
                'name': 'Videolar',
                'description': 'Video fayllar va ko\'rsatmalar',
                'icon': 'fas fa-video'
            },
            {
                'name': 'Audio',
                'description': 'Audio fayllar va ovozli ma\'lumotlar',
                'icon': 'fas fa-music'
            },
            {
                'name': 'Arxivlar',
                'description': 'Siqilgan fayllar va arxivlar',
                'icon': 'fas fa-archive'
            },
            {
                'name': 'Jadvallar',
                'description': 'Excel jadvallar va ma\'lumotlar',
                'icon': 'fas fa-table'
            },
            {
                'name': 'Ta\'lim',
                'description': 'Ta\'lim materiallari va darslar',
                'icon': 'fas fa-graduation-cap'
            },
            {
                'name': 'Texnik',
                'description': 'Texnik hujjatlar va diagrammalar',
                'icon': 'fas fa-cogs'
            },
            {
                'name': 'Boshqa',
                'description': 'Boshqa turdagi fayllar',
                'icon': 'fas fa-file'
            }
        ]

        created_count = 0
        for category_data in categories:
            category, created = DocumentCategory.objects.get_or_create(
                name=category_data['name'],
                defaults={
                    'description': category_data['description'],
                    'icon': category_data['icon']
                }
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created category: {category.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Category already exists: {category.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully set up {created_count} new categories')
        ) 