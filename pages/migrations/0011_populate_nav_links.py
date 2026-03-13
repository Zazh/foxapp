from django.db import migrations


def populate_nav_links(apps, schema_editor):
    NavLink = apps.get_model('pages', 'NavLink')
    links = [
        {'title_en': 'Home', 'title_ru': 'Главная', 'title_ar': 'الرئيسية', 'url': '/', 'sort_order': 0},
        {'title_en': 'About', 'title_ru': 'О нас', 'title_ar': 'حول', 'url': '/about/', 'sort_order': 1},
        {'title_en': 'Parking', 'title_ru': 'Парковка', 'title_ar': 'موقف سيارات', 'url': '/services/auto/standard/', 'sort_order': 2},
        {'title_en': 'Contacts', 'title_ru': 'Контакты', 'title_ar': 'اتصل بنا', 'url': '/contacts/', 'sort_order': 3},
    ]
    for link_data in links:
        NavLink.objects.create(**link_data)


def reverse_nav_links(apps, schema_editor):
    NavLink = apps.get_model('pages', 'NavLink')
    NavLink.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0010_navlink'),
    ]

    operations = [
        migrations.RunPython(populate_nav_links, reverse_nav_links),
    ]
