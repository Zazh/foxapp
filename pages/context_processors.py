from .models import FeedbackCTA


def feedback_cta(request):
    return {'feedback_cta': FeedbackCTA.load()}
