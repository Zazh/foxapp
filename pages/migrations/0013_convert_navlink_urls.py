from django.db import migrations


URL_TO_PAGE = {
    '/': 'home',
    '/about/': 'about',
    '/contacts/': 'contacts',
}


def convert_urls(apps, schema_editor):
    NavLink = apps.get_model('pages', 'NavLink')
    for link in NavLink.objects.all():
        # Check old url field value stored in custom_url after field rename
        page = URL_TO_PAGE.get(link.custom_url, None)
        if page:
            link.page = page
            link.custom_url = ''
        else:
            link.page = 'custom'
        link.save()


class Migration(migrations.Migration):

    dependencies = [
        ('pages', '0012_remove_navlink_url_navlink_custom_url_navlink_page'),
    ]

    operations = [
        migrations.RunPython(convert_urls, migrations.RunPython.noop),
    ]
