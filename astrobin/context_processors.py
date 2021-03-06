from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils.translation import ugettext as _

from haystack.query import SearchQuerySet
from notification import models as notifications
from toggleproperties.models import ToggleProperty
from persistent_messages.models import Message

from astrobin.models import Request
from astrobin.models import Gear
from astrobin.models import Image

from nested_comments.models import NestedComment


def privatebeta_enabled(request):
    return {'privatebeta_enabled': settings.PRIVATEBETA_ENABLE_BETA}


def notices_count(request):
    response = {}
    if request.user.is_authenticated():
        response['notifications_count'] = Message.objects.filter(user = request.user, read = False).count()

    return response


def user_language(request):
    d = {
        'user_language': request.LANGUAGE_CODE,
    }
    if request.user.is_authenticated():
        profile = request.user.userprofile
        d['user_language'] = profile.language

    return d


def user_profile(request):
    d = {
        'userprofile': None,
    }

    if request.user.is_authenticated():
        profile = request.user.userprofile
        d['userprofile'] = profile

    return d


def user_scores(request):
    scores = {
        'user_scores_index': 0,
        'user_scores_followers': 0,
    }

    if request.user.is_authenticated():
        cache_key = "astrobin_user_score_%s" % request.user
        scores = cache.get(cache_key)
        user = User.objects.get(pk = request.user.pk) # The lazy object in the request won't do

        if not scores:
            try:
                user_search_result =\
                    SearchQuerySet().models(User).filter(django_id = request.user.pk)[0]
            except IndexError:
                return {
                    'user_scores_index': 0,
                    'user_scores_followers': 0
                }

            index = user_search_result.normalized_likes
            followers = user_search_result.followers

            scores = {}
            scores['user_scores_index'] = index
            scores['user_scores_followers'] = followers
            cache.set(cache_key, scores, 43200)

    return scores


def common_variables(request):
    from rawdata.utils import user_has_active_subscription
    from django_user_agents.utils import get_and_set_user_agent

    get_and_set_user_agent(request)

    d = {
        #'random_gear_item': Gear.objects.filter(moderator_fixed = None).order_by('?')[:1].get(),
        'is_producer': request.user.groups.filter(name='Producers'),
        'is_retailer': request.user.groups.filter(name='Retailers'),
        'has_rawdata_subscription': user_has_active_subscription(request.user),
        'is_iotd_staff': request.user.groups.filter(name='IOTD_Staff'),
        'IMAGES_URL' : settings.IMAGES_URL,
        'ADS_ENABLED': settings.ADS_ENABLED,
        'DONATIONS_ENABLED': settings.DONATIONS_ENABLED,
    }

    return d

