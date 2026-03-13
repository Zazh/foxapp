from modeltranslation.translator import translator, TranslationOptions
from .models import Policy


class PolicyTranslationOptions(TranslationOptions):
    fields = ('title', 'content', 'consent_label')


translator.register(Policy, PolicyTranslationOptions)
