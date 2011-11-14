from datetime import datetime

from django.template.defaultfilters import timesince
from django.utils.translation import ugettext as _
from django import template
from django.template import Library, Node
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils.safestring import mark_safe

from django.utils.encoding import force_unicode
from django.utils.functional import allow_lazy
from django.template.defaultfilters import stringfilter

from notification import models as notifications
from persistent_messages import models as messages
from celery.result import AsyncResult

from astrobin.models import Request

register = Library() 

@register.simple_tag
def current(request, pattern):
    import re
    if re.search(pattern, request.path):
        return 'current'
    return ''


@register.inclusion_tag('inclusion_tags/image_list.html')
def image_list(request, object_list):
    paginator = Paginator(object_list, 20)

    page = request.GET.get('p')
    try:
        images = paginator.page(page)
    except (TypeError, PageNotAnInteger):
        images = paginator.page(1)
    except EmptyPage:
        images = paginator.page(paginator.num_pages)

    return {'images': images,
            'thumbnail_size':settings.THUMBNAIL_SIZE,
            's3_url':settings.S3_URL,
            'query':request.GET.get('q'),
           }


@register.inclusion_tag('inclusion_tags/related_images.html')
def related_images(request, object_list, type):
    paginator = Paginator(object_list, 10)

    page = request.GET.get('p')
    try:
        images = paginator.page(page)
    except (TypeError, PageNotAnInteger):
        images = paginator.page(1)
    except EmptyPage:
        images = paginator.page(paginator.num_pages)

    return {
            'request': request,
            'images': images,
            'small_thumbnail_size':settings.SMALL_THUMBNAIL_SIZE,
            's3_url':settings.S3_URL,
            'related_type': type,
           }


@register.inclusion_tag('inclusion_tags/notification_list.html')
def notification_list(request, show_footer = True, limit = 0):
    ret = notifications.Notice.objects.filter(user=request.user)
    if limit > 0:
        ret = ret[:limit]
    return {
        'notifications':ret,
        'show_footer':show_footer}


@register.inclusion_tag('inclusion_tags/message_list.html')
def message_list(request, show_footer = True):
    return {
        'messages':messages.Message.objects.filter(user=request.user).order_by('-created')[:10],
        'show_footer':show_footer}


@register.inclusion_tag('inclusion_tags/request_list.html')
def request_list(request, show_footer = True):
    return {
        'requests':Request.objects.filter(to_user=request.user).order_by('-created').select_subclasses()[:10],
        'show_footer':show_footer}


@register.simple_tag
def notifications_icon(request):
    basepath = '/static/icons/iconic/orange/'
    if notifications.Notice.objects.filter(user=request.user).filter(unseen=True):
        return basepath + 'new_notifications.png'
    else:
        return basepath + 'notifications.png'


@register.simple_tag
def messages_icon(request):
    basepath = '/static/icons/iconic/orange/'
    if messages.Message.objects.filter(user=request.user).filter(read=False):
        return basepath + 'new_messages.png'
    else:
        return basepath + 'messages.png'


@register.simple_tag
def requests_icon(request):
    basepath = '/static/icons/iconic/orange/'
    if Request.objects.filter(to_user=request.user).filter(fulfilled=False):
        return basepath + 'new_requests.png'
    else:
        return basepath + 'requests.png'


@register.filter
def append_slash(value):
    return value.replace('\n', '\\\n')


@register.simple_tag
def image_is_ready(image):
    return AsyncResult(image.store_task_id).ready()


@register.inclusion_tag('inclusion_tags/form_saved.html')
def form_saved(request):
    return {'saved': 'saved' in request.GET}


@register.filter
def ago(date_time):
    date_time = date_time.replace(tzinfo = None)
    diff = abs(date_time - datetime.today())
    if diff.days <= 0:
        span = timesince(date_time)
        span = span.split(",")[0] # just the most significant digit
        if span == "0 " + _("minutes"):
            return _("seconds ago")
        return _("%s ago") % span 
    return datetime.date(date_time)  


@register.tag
def query_string(parser, token):
    """
    Allows you too manipulate the query string of a page by adding and removing keywords.
    If a given value is a context variable it will resolve it.
    Based on similiar snippet by user "dnordberg".
    
    requires you to add:
    
    TEMPLATE_CONTEXT_PROCESSORS = (
    'django.core.context_processors.request',
    )
    
    to your django settings. 
    
    Usage:
    http://www.url.com/{% query_string "param_to_add=value, param_to_add=value" "param_to_remove, params_to_remove" %}
    
    Example:
    http://www.url.com/{% query_string "" "filter" %}filter={{new_filter}}
    http://www.url.com/{% query_string "page=page_obj.number" "sort" %} 
    
    """
    try:
        tag_name, add_string,remove_string = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, "%r tag requires two arguments" % token.contents.split()[0]
    if not (add_string[0] == add_string[-1] and add_string[0] in ('"', "'")) or not (remove_string[0] == remove_string[-1] and remove_string[0] in ('"', "'")):
        raise template.TemplateSyntaxError, "%r tag's argument should be in quotes" % tag_name
    
    add = string_to_dict(add_string[1:-1])
    remove = string_to_list(remove_string[1:-1])
    
    return QueryStringNode(add,remove)

class QueryStringNode(Node):
    def __init__(self, add,remove):
        self.add = add
        self.remove = remove
        
    def render(self, context):
        p = {}
        for k, v in context["request"].GET.items():
            p[k]=v
        return get_query_string(p,self.add,self.remove,context)

def get_query_string(p, new_params, remove, context):
    """
    Add and remove query parameters. From `django.contrib.admin`.
    """
    for r in remove:
        for k in p.keys():
            if k.startswith(r):
                del p[k]
    for k, v in new_params.items():
        if k in p and v is None:
            del p[k]
        elif v is not None:
            p[k] = v
            
    for k, v in p.items():
        try:
            p[k] = template.Variable(v).resolve(context)
        except:
            p[k]=v
                
    return mark_safe('?' + '&amp;'.join([u'%s=%s' % (k, v) for k, v in p.items()]).replace(' ', '%20'))

# Taken from lib/utils.py   
def string_to_dict(string):
    kwargs = {}
    
    if string:
        string = str(string)
        if ',' not in string:
            # ensure at least one ','
            string += ','
        for arg in string.split(','):
            arg = arg.strip()
            if arg == '': continue
            kw, val = arg.split('=', 1)
            kwargs[kw] = val
    return kwargs

def string_to_list(string):
    args = []
    if string:
        string = str(string)
        if ',' not in string:
            # ensure at least one ','
            string += ','
        for arg in string.split(','):
            arg = arg.strip()
            if arg == '': continue
            args.append(arg)
    return args


@register.filter
def string_to_date(date):
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except:
        return datetime.now()
        

def truncate_chars(s, num):
    """
    Template filter to truncate a string to at most num characters respecting word
    boundaries.
    """
    s = force_unicode(s)
    length = int(num)
    if len(s) > length:
        length = length - 4
        if s[length-1] == ' ' or s[length] == ' ':
            s = s[:length].strip()
        else:
            words = s[:length].split()
            if len(words) > 1:
                del words[-1]
            s = u' '.join(words)
        s += ' ...'
    return s
truncate_chars = allow_lazy(truncate_chars, unicode)

@register.filter
def truncatechars(value, arg):
    """
    Truncates a string after a certain number of characters, but respects word boundaries.
    
    Argument: Number of characters to truncate after.
    """
    try:
        length = int(arg)
    except ValueError: # If the argument is not a valid integer.
        return value # Fail silently.
    return truncate_chars(value, length)
truncatechars.is_safe = True
truncatechars = stringfilter(truncatechars)

