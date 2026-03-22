from django import template
from django.conf import settings
from django.urls import translate_url
from django.utils.html import format_html_join, format_html

register = template.Library()


@register.simple_tag(takes_context=True)
def canonical_url(context):
    request = context.get('request')
    if not request:
        return ''
    return request.build_absolute_uri(request.path)


@register.simple_tag(takes_context=True)
def hreflang_tags(context):
    request = context.get('request')
    if not request:
        return ''

    path = request.path
    tags = []

    for lang_code, lang_name in settings.LANGUAGES:
        alt_path = translate_url(path, lang_code)
        alt_url = request.build_absolute_uri(alt_path)
        tags.append(format_html(
            '<link rel="alternate" hreflang="{}" href="{}">',
            lang_code, alt_url,
        ))

    # x-default points to default language (en)
    default_path = translate_url(path, settings.LANGUAGE_CODE)
    default_url = request.build_absolute_uri(default_path)
    tags.append(format_html(
        '<link rel="alternate" hreflang="x-default" href="{}">',
        default_url,
    ))

    # Canonical = current language URL
    canonical = request.build_absolute_uri(path)
    tags.append(format_html(
        '<link rel="canonical" href="{}">',
        canonical,
    ))

    return format_html('\n    '.join(str(t) for t in tags))
