import time
from django.conf import settings

def cache_buster(request):
    if settings.DEBUG:
        return {'CACHE_BUSTER': int(time.time())}
    return {'CACHE_BUSTER': ''}