from django.views.generic import DetailView
from .models import Policy


class PolicyDetailView(DetailView):
    model = Policy
    template_name = 'public/content/policy_detail.html'
    context_object_name = 'policy'

    def get_queryset(self):
        return Policy.objects.filter(is_active=True)
