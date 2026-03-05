from django.views.generic import TemplateView
from .models import HomePage, AboutPage, ContactsPage


class HomePageView(TemplateView):
    template_name = 'public/content/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = HomePage.load()
        context['page'] = page
        context['benefits'] = page.benefits.all()
        context['gallery_slides'] = page.gallery_slides.all()
        context['dashboard_features'] = page.dashboard_features.all()
        return context


class AboutPageView(TemplateView):
    template_name = 'public/content/about.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = AboutPage.load()
        context['page'] = page
        context['offer_items'] = page.offer_items.all()
        return context


class ContactsPageView(TemplateView):
    template_name = 'public/content/contacts.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = ContactsPage.load()
        context['page'] = page
        context['info_items'] = page.info_items.all()
        return context
