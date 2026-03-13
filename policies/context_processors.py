from .models import Policy


def footer_policies(request):
    return {
        'footer_policies': Policy.objects.filter(is_active=True).only('title', 'slug')
    }
