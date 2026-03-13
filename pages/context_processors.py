from .models import FeedbackCTA, NavLink, SocialLink


def feedback_cta(request):
    return {'feedback_cta': FeedbackCTA.load()}


def nav_links(request):
    return {
        'nav_links': NavLink.objects.filter(is_active=True)
    }


def social_links(request):
    links = SocialLink.objects.filter(is_active=True)
    whatsapp = links.filter(platform='whatsapp').first()
    return {
        'social_links': links,
        'whatsapp_url': whatsapp.url if whatsapp else '',
    }
