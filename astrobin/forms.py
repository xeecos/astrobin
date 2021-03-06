from django import forms
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.datastructures import MultiValueDictKeyError

from haystack.forms import SearchForm
from haystack.query import SearchQuerySet, EmptySearchQuerySet
from haystack.query import SQ

from models import *
from utils import affiliate_limit, retailer_affiliate_limit

import string
import unicodedata
import operator
import datetime

from management import NOTICE_TYPES

def uniq(seq):
    # Not order preserving
    keys = {}
    for e in seq:
        keys[e] = 1
    return keys.keys()

def uniq_id_tuple(seq):
    seen = set()
    ret = []
    for e in seq:
        id = e[0]
        if id not in seen:
            seen.add(id)
            ret.append(e)
    return ret


class ImageUploadForm(forms.ModelForm):
    class Meta:
        model = Image
        fields = ('image_file',)


class ImageEditBasicForm(forms.ModelForm):
    error_css_class = 'error'

    link = forms.RegexField(
        regex = '^(http|https)://',
        required = False,
        help_text = _("If you're hosting a copy of this image on your website, put the address here."),
        error_messages = {'invalid': "The address must start with http:// or https://."},
    )
    link_to_fits = forms.RegexField(
        regex = '^(http|https)://',
        required = False,
        help_text = _("If you want to share the TIFF or FITS file of your image, put a link to the file here. Unfortunately, AstroBin cannot offer to store these files at the moment, so you will have to host them on your personal space."),
        error_messages = {'invalid': "The address must start with http:// or https://."},
    )

    def __init__(self, user=None, **kwargs):
        super(ImageEditBasicForm, self).__init__(**kwargs)
        self.fields['link'].label = _("Link")
        self.fields['link_to_fits'].label = _("Link to TIFF/FITS")
        self.fields['locations'].label = _("Locations")

        profile = user.userprofile
        locations = Location.objects.filter(user = profile)
        self.fields['locations'].queryset = locations
        self.fields['locations'].required = False

    def clean_link(self):
        return self.cleaned_data['link'].strip()

    def clean_subject_type(self):
        subject_type = self.cleaned_data['subject_type']
        if subject_type == 0:
            raise forms.ValidationError(_('This field is required.'))

        return self.cleaned_data['subject_type']

    class Meta:
        model = Image
        fields = ('title', 'link', 'link_to_fits', 'subject_type', 'solar_system_main_subject', 'locations', 'description')


class ImageEditWatermarkForm(forms.ModelForm):
    error_css_class = 'error'

    watermark_opacity = forms.IntegerField(
        label = _("Opacity"),
        help_text = _("0 means invisible; 100 means completely opaque. Recommended values are: 10 if the watermark will appear on the dark sky background, 50 if on some bright object."),
        min_value = 0,
        max_value = 100,
    )

    def __init__(self, user=None, **kwargs):
        super(ImageEditWatermarkForm, self).__init__(**kwargs)

    def clean_watermark_text(self):
        data = self.cleaned_data['watermark_text']
        watermark = self.cleaned_data['watermark']

        if watermark and data == '':
            raise forms.ValidationError(_("If you want to watermark this image, you must specify some text."));

        return data.strip()

    class Meta:
        model = Image
        fields = ('watermark', 'watermark_text', 'watermark_position', 'watermark_opacity',)


class ImageEditGearForm(forms.ModelForm):
    def __init__(self, user=None, **kwargs):
        super(ImageEditGearForm, self).__init__(**kwargs)
        profile = user.userprofile
        telescopes = profile.telescopes.all()
        self.fields['imaging_telescopes'].queryset = telescopes
        self.fields['guiding_telescopes'].queryset = telescopes
        cameras = profile.cameras.all()
        self.fields['imaging_cameras'].queryset = cameras
        self.fields['guiding_cameras'].queryset = cameras
        for attr in ('mounts',
                     'focal_reducers',
                     'software',
                     'filters',
                     'accessories',
                    ):
            self.fields[attr].queryset = getattr(profile, attr).all()

        self.fields['imaging_telescopes'].label = _("Imaging telescopes or lenses")
        self.fields['guiding_telescopes'].label = _("Guiding telescopes or lenses")
        self.fields['mounts'].label = _("Mounts")
        self.fields['imaging_cameras'].label = _("Imaging cameras")
        self.fields['guiding_cameras'].label = _("Guiding cameras")
        self.fields['focal_reducers'].label = _("Focal reducers")
        self.fields['software'].label = _("Software")
        self.fields['filters'].label = _("Filters")
        self.fields['accessories'].label = _("Accessories")

    class Meta:
        model = Image
        fields = ('imaging_telescopes',
                  'guiding_telescopes',
                  'mounts',
                  'imaging_cameras',
                  'guiding_cameras',
                  'focal_reducers',
                  'software',
                  'filters',
                  'accessories',
                 )


class UserProfileEditBasicForm(forms.ModelForm):
    error_css_class = 'error'

    website = forms.RegexField(
        regex = '^(http|https)://',
        required = False,
        help_text = _("If you have a personal website, put the address here."),
        error_messages = {'invalid': "The address must start with http:// or https://."},
    )

    class Meta:
        model = UserProfile
        fields = ('real_name', 'website', 'job', 'hobbies', 'timezone', 'about')

    def __init__(self, **kwargs):
        super(UserProfileEditBasicForm, self).__init__(**kwargs)
        self.fields['website'].label = _("Website")


class UserProfileEditCommercialForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = UserProfile
        fields = ('company_name', 'company_description', 'company_website',)


class UserProfileEditRetailerForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = UserProfile
        fields = (
            'retailer_country',
        )


class UserProfileEditGearForm(forms.Form):
    telescopes = forms.CharField(
        max_length=256,
        help_text=_("All the telescopes and lenses you own, including the ones you use for guiding, go here."),
        required=False)

    mounts = forms.CharField(
        max_length=256,
        required=False)

    cameras = forms.CharField(
        max_length=256,
        help_text=_("Your DSLRs, CCDs, planetary cameras and guiding cameras go here."),
        required=False)

    focal_reducers = forms.CharField(
        max_length=256,
        required=False)

    software = forms.CharField(
        max_length=256,
        required=False)

    filters = forms.CharField(
        max_length=256,
        help_text=_("Hint: enter your filters separately! If you enter, for instance, LRGB in one box, you won't be able to add separate acquisition sessions for them."),
        required=False)

    accessories = forms.CharField(
        max_length=256,
        required=False)

    def __init__(self, user=None, **kwargs):
        super(UserProfileEditGearForm, self).__init__(**kwargs)
        self.fields['telescopes'].label = _("Telescopes and lenses")
        self.fields['mounts'].label = _("Mounts")
        self.fields['cameras'].label = _("Cameras")
        self.fields['focal_reducers'].label = _("Focal reducers")
        self.fields['software'].label = _("Software")
        self.fields['filters'].label = _("Filters")
        self.fields['accessories'].label = _("Accessories")


class UserProfileEditPreferencesForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['language',]

    def __init__(self, user=None, **kwargs):
        super(UserProfileEditPreferencesForm, self).__init__(**kwargs)
        for notice_type in NOTICE_TYPES:
            if notice_type[3] == 2:
                self.fields[notice_type[0]] = forms.BooleanField(
                    label=_(notice_type[1]),
                    required=False
                )


class PrivateMessageForm(forms.Form):
    subject = forms.CharField(max_length=255, required=False)
    body = forms.CharField(widget=forms.Textarea, max_length=4096, required=False)


class BringToAttentionForm(forms.Form):
    users = forms.CharField(max_length=64, required=False)

    def __init__(self, user=None, **kwargs):
        super(BringToAttentionForm, self).__init__(**kwargs)
        self.fields['users'].label = _("Users")


class ImageRevisionUploadForm(forms.ModelForm):
    class Meta:
        model = ImageRevision
        fields = ('image_file',)


class AdvancedSearchForm(SearchForm):
    search_type = forms.ChoiceField(
        required = True,
        label = _("Search type"),
        choices = (
            (0, _("All")),
            (1, _("Images")),
            (2, _("Users")),
            (3, _("Gear")),
        ),
        initial = 0,
    )

    solar_system_main_subject = forms.ChoiceField(
        required = False,
        choices = (('', '---------'),) + SOLAR_SYSTEM_SUBJECT_CHOICES,
    )

    telescope_type = forms.MultipleChoiceField(
        required = False,
        label = _("Telescope type"),
        choices = (('any', _("Any")),) + Telescope.TELESCOPE_TYPES,
        initial = ['any'] + [x[0] for x in Telescope.TELESCOPE_TYPES],
    )
    camera_type = forms.MultipleChoiceField(
        required = False,
        label = _("Camera type"),
        choices = (('any', _("Any")),) + Camera.CAMERA_TYPES,
        initial = ['any'] + [x[0] for x in Camera.CAMERA_TYPES],
    )

    imaging_telescopes = forms.CharField(
        required = False
    )
    imaging_cameras = forms.CharField(
        required = False
    )

    aperture_min = forms.IntegerField(
        required = False,
        help_text = _("Express value in mm"),
        min_value = 0,
    )
    aperture_max = forms.IntegerField(
        required = False,
        help_text = _("Express value in mm"),
        min_value = 0,
    )

    pixel_size_min = forms.IntegerField(
        required = False,
        help_text = _("Express value in &mu;m"),
        min_value = 0,
    )
    pixel_size_max = forms.IntegerField(
        required = False,
        help_text = _("Express value in &mu;m"),
        min_value = 0,
    )

    start_date = forms.DateField(
        required=False,
        widget=forms.TextInput(attrs={'class':'datepickerclass'}),
        help_text=_("Please use the following format: yyyy-mm-dd"))

    end_date = forms.DateField(
        required=False,
        widget=forms.TextInput(attrs={'class':'datepickerclass'}),
        help_text=_("Please use the following format: yyyy-mm-dd"))

    integration_min = forms.FloatField(
        required=False,
        help_text=_("Express value in hours"))

    integration_max = forms.FloatField(
        required=False,
        help_text=_("Express value in hours"))

    moon_phase_min = forms.FloatField(
        required=False,
        help_text="0-100")

    moon_phase_max = forms.FloatField(
        required=False,
        help_text="0-100")

    license = forms.MultipleChoiceField(
        required = False,
        label = _("License"),
        choices = LICENSE_CHOICES,
        initial = [x[0] for x in LICENSE_CHOICES],
    )

    def __init__(self, data=None, **kwargs):
        super(AdvancedSearchForm, self).__init__(data, **kwargs)
        self.fields['q'].help_text = _("Search for astronomical objects, telescopes or lenses, cameras, filters...")

        self.fields['solar_system_main_subject'].label = _("Main solar system subject")
        self.fields['imaging_telescopes'].label = _("Imaging telescopes or lenses")
        self.fields['imaging_cameras'].label = _("Imaging cameras")
        self.fields['aperture_min'].label = _("Min. telescope aperture")
        self.fields['aperture_max'].label = _("Max. telescope aperture")
        self.fields['start_date'].label = _("Acquired after")
        self.fields['end_date'].label = _("Acquired before")
        self.fields['integration_min'].label = _("Min. integration")
        self.fields['integration_max'].label = _("Max. integration")
        self.fields['moon_phase_min'].label = _("Min. Moon phase %")
        self.fields['moon_phase_max'].label = _("Max. Moon phase %")

    def search(self):
        sqs = EmptySearchQuerySet()
        user_sqs = EmptySearchQuerySet()
        image_sqs = EmptySearchQuerySet()
        gear_sqs = EmptySearchQuerySet()

        if not self.is_valid():
            return EmptySearchQuerySet()

        if self.cleaned_data['q'] == '':
            sqs = SearchQuerySet().models(User, Image, Gear).all()
            user_sqs = SearchQuerySet().models(User).all()
            image_sqs = SearchQuerySet().models(Image).all()
            gear_sqs = SearchQuerySet().models(Gear).all()
            if self.load_all:
                sqs = sqs.load_all()
                user_sqs = user_sqs.load_all()
                image_sqs = image_sqs.load_all()
                gear_sqs = gear_sqs.load_all()
        else:
            sqs = super(AdvancedSearchForm, self).search().models(User, Image, Gear)
            user_sqs = super(AdvancedSearchForm, self).search().models(User)
            image_sqs = super(AdvancedSearchForm, self).search().models(Image)
            gear_sqs = super(AdvancedSearchForm, self).search().models(Gear)

        # This section deals with properties common to all the search indexes.
        if self.cleaned_data['start_date']:
            sqs = sqs.filter(last_acquisition_date__gte=self.cleaned_data['start_date'])
            user_sqs = user_sqs.filter(last_acquisition_date__gte=self.cleaned_data['start_date'])
            image_sqs = image_sqs.filter(last_acquisition_date__gte=self.cleaned_data['start_date'])

        if self.cleaned_data['end_date']:
            sqs = sqs.filter(first_acquisition_date__lte=self.cleaned_data['end_date'])
            user_sqs = user_sqs.filter(first_acquisition_date__lte=self.cleaned_data['end_date'])
            image_sqs = image_sqs.filter(first_acquisition_date__lte=self.cleaned_data['end_date'])

        if self.cleaned_data['telescope_type'] and 'any' not in self.cleaned_data['telescope_type']:
            filters = reduce(operator.or_, [SQ(**{'telescope_types': x}) for x in self.cleaned_data['telescope_type']])
            sqs = sqs.filter(filters)
            user_sqs = user_sqs.filter(filters)
            image_sqs = image_sqs.filter(filters)
        elif not self.cleaned_data['telescope_type']:
            sqs = EmptySearchQuerySet()
            user_sqs = EmptySearchQuerySet()
            image_sqs = EmptySearchQuerySet()

        if self.cleaned_data['camera_type'] and 'any' not in self.cleaned_data['camera_type']:
            filters = reduce(operator.or_, [SQ(**{'camera_types': x}) for x in self.cleaned_data['camera_type']])
            sqs = sqs.filter(filters)
            user_sqs = user_sqs.filter(filters)
            image_sqs = image_sqs.filter(filters)
        elif not self.cleaned_data['camera_type']:
            sqs = EmptySearchQuerySet()
            user_sqs = EmptySearchQuerySet()
            image_sqs = EmptySearchQuerySet()

        if self.cleaned_data['aperture_min'] is not None:
            sqs = sqs.filter(min_aperture__gte = self.cleaned_data['aperture_min'])
            user_sqs = user_sqs.filter(min_aperture__gte = self.cleaned_data['aperture_min'])
            image_sqs = image_sqs.filter(min_aperture__gte = self.cleaned_data['aperture_min'])

        if self.cleaned_data['aperture_max'] is not None:
            sqs = sqs.filter(max_aperture__lte = self.cleaned_data['aperture_max'])
            user_sqs = user_sqs.filter(max_aperture__lte = self.cleaned_data['aperture_max'])
            image_sqs = image_sqs.filter(max_aperture__lte = self.cleaned_data['aperture_max'])

        if self.cleaned_data['pixel_size_min'] is not None:
            sqs = sqs.filter(min_pixel_size__gte = self.cleaned_data['pixel_size_min'])
            user_sqs = user_sqs.filter(min_pixel_size__gte = self.cleaned_data['pixel_size_min'])
            image_sqs = image_sqs.filter(min_pixel_size__gte = self.cleaned_data['pixel_size_min'])

        if self.cleaned_data['pixel_size_max'] is not None:
            sqs = sqs.filter(max_pixel_size__lte = self.cleaned_data['pixel_size_max'])
            user_sqs = user_sqs.filter(max_pixel_size__lte = self.cleaned_data['pixel_size_max'])
            image_sqs = image_sqs.filter(max_pixel_size__lte = self.cleaned_data['pixel_size_max'])

        if self.cleaned_data['integration_min']:
            sqs = sqs.filter(integration__gte=int(self.cleaned_data['integration_min'] * 3600))
            user_sqs = user_sqs.filter(integration__gte=int(self.cleaned_data['integration_min'] * 3600))
            image_sqs = image_sqs.filter(integration__gte=int(self.cleaned_data['integration_min'] * 3600))

        if self.cleaned_data['integration_max']:
            sqs = sqs.filter(integration__lte=int(self.cleaned_data['integration_max'] * 3600))
            user_sqs = user_sqs.filter(integration__lte=int(self.cleaned_data['integration_max'] * 3600))
            image_sqs = image_sqs.filter(integration__lte=int(self.cleaned_data['integration_max'] * 3600))

        if self.cleaned_data['moon_phase_min']:
            sqs = sqs.filter(moon_phase__gte=self.cleaned_data['moon_phase_min'])
            user_sqs = user_sqs.filter(moon_phase__gte=self.cleaned_data['moon_phase_min'])
            image_sqs = image_sqs.filter(moon_phase__gte=self.cleaned_data['moon_phase_min'])

        if self.cleaned_data['moon_phase_max']:
            sqs = sqs.filter(moon_phase__lte=self.cleaned_data['moon_phase_max'])
            user_sqs = user_sqs.filter(moon_phase__lte=self.cleaned_data['moon_phase_max'])
            image_sqs = image_sqs.filter(moon_phase__lte=self.cleaned_data['moon_phase_max'])

        # This section deals with properties of the Image search index:
        if self.cleaned_data['solar_system_main_subject']:
            image_sqs = image_sqs.filter(solar_system_main_subject = self.cleaned_data['solar_system_main_subject'])
            user_sqs = EmptySearchQuerySet()
            gear_sqs = EmptySearchQuerySet()
            sqs = EmptySearchQuerySet()

        if self.cleaned_data['license']:
            filters = reduce(operator.or_, [SQ(**{'license': x}) for x in self.cleaned_data['license']])
            image_sqs = image_sqs.filter(filters)
        else:
            image_sqs = EmptySearchQuerySet()

        # This section deals with properties of the User search index.
        # TODO

        # This section deals with properties of the Gear search index.
        # TODO

        if self.cleaned_data['q'] == '' and self.cleaned_data['solar_system_main_subject'] == None:
            sqs = SearchQuerySet().models(Image, User, Gear).all()
        elif self.cleaned_data['solar_system_main_subject']:
            sqs = image_sqs
        else:
            sqs = sqs | user_sqs | image_sqs | gear_sqs

        search_type = self.cleaned_data['search_type']
        if search_type == '1':
            sqs = sqs.filter(django_ct = 'astrobin.image')
        elif search_type == '2':
            sqs = sqs.filter(django_ct = 'auth.user')
        elif search_type == '3':
            sqs = sqs.filter(django_ct = 'astrobin.gear')

        return sqs


class LocationEditForm(forms.ModelForm):
    error_css_class = 'error'

    lat_deg = forms.IntegerField(
        label = _("Latitude (degrees)"),
        help_text = "(0-90)",
        max_value = 90,
        min_value = 0)
    lat_min = forms.IntegerField(
        label = _("Latitude (minutes)"),
        help_text = "(0-60)",
        max_value = 60,
        min_value = 0,
        required = False)
    lat_sec = forms.IntegerField(
        label = _("Latitude (seconds)"),
        help_text = "(0-60)",
        max_value = 60,
        min_value = 0,
        required = False)

    lon_deg = forms.IntegerField(
        label = _("Longitude (degrees)"),
        help_text = "(0-180)",
        max_value = 180,
        min_value = 0)
    lon_min = forms.IntegerField(
        label = _("Longitude (minutes)"),
        help_text = "(0-60)",
        max_value = 60,
        min_value = 0,
        required = False)
    lon_sec = forms.IntegerField(
        label = _("Longitude (seconds)"),
        help_text = "(0-60)",
        max_value = 60,
        min_value = 0,
        required = False)

    def __init__(self, **kwargs):
        super(LocationEditForm, self).__init__(**kwargs)
        self.fields['country'].choices = sorted(COUNTRIES, key = lambda c: c[1])

    class Meta:
        model = Location


class SolarSystem_AcquisitionForm(forms.ModelForm):
    error_css_class = 'error'

    date = forms.DateField(
        required=False,
        input_formats = ['%Y-%m-%d'],
        widget=forms.TextInput(attrs={'class':'datepickerclass'}),
        help_text=_("Please use the following format: yyyy-mm-dd"),
        label = _("Date"),
    )

    def clean_seeing(self):
        data = self.cleaned_data['seeing']
        if data and data not in range(1, 6):
            raise forms.ValidationError(_("Please enter a value between 1 and 5."))

        return data

    def clean_transparency(self):
        data = self.cleaned_data['transparency']
        if data and data not in range(1, 11):
            raise forms.ValidationError(_("Please enter a value between 1 and 10."))

        return data

    class Meta:
        model = SolarSystem_Acquisition
        fields = (
            'date',
            'time',
            'frames',
            'fps',
            'focal_length',
            'cmi',
            'cmii',
            'cmiii',
            'seeing',
            'transparency',
        )
        widgets = {
            'date': forms.TextInput(attrs={'class': 'datepickerclass'}),
            'time': forms.TextInput(attrs={'class': 'timepickerclass'}),
        }


class DeepSky_AcquisitionForm(forms.ModelForm):
    error_css_class = 'error'

    date = forms.DateField(
        required=False,
        input_formats = ['%Y-%m-%d'],
        widget=forms.TextInput(attrs={'class':'datepickerclass'}),
        help_text=_("Please use the following format: yyyy-mm-dd"),
        label = _("Date"),
    )

    class Meta:
        model = DeepSky_Acquisition

    def __init__(self, user=None, **kwargs):
        queryset = None
        try:
            queryset = kwargs.pop('queryset')
        except KeyError:
            pass

        super(DeepSky_AcquisitionForm, self).__init__(**kwargs)
        if queryset:
            self.fields['filter'].queryset = queryset
        self.fields['number'].required = True
        self.fields['duration'].required = True

    def save(self, force_insert=False, force_update=False, commit=True):
        m = super(DeepSky_AcquisitionForm, self).save(commit=False)
        m.advanced = True
        if commit:
            m.save()
        return m

    def clean_date(self):
        date = self.cleaned_data['date']
        if date and date > datetime.date.today():
            raise forms.ValidationError(_("The date cannot be in the future."))
        return date


class DeepSky_AcquisitionBasicForm(forms.ModelForm):
    error_css_class = 'error'

    date = forms.DateField(
        required=False,
        input_formats = ['%Y-%m-%d'],
        widget=forms.TextInput(attrs={'class':'datepickerclass'}),
        help_text=_("Please use the following format: yyyy-mm-dd"),
        label = _("Date"),
    )

    def clean_date(self):
        date = self.cleaned_data['date']
        if date and date > datetime.date.today():
            raise forms.ValidationError(_("The date cannot be in the future."))
        return date

    class Meta:
        model = DeepSky_Acquisition
        fields = ('date', 'number', 'duration',)
        widgets = {
            'date': forms.TextInput(attrs={'class': 'datepickerclass'}),
        }


class DefaultImageLicenseForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('default_license',)


class ImageLicenseForm(forms.ModelForm):
    class Meta:
        model = Image
        fields = ('license',)


class TelescopeEditForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Telescope
        exclude = ('make', 'name', 'retailed')

class MountEditForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Mount
        exclude = ('make', 'name', 'retailed')


class CameraEditForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Camera
        exclude = ('make', 'name', 'retailed')


class FocalReducerEditForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = FocalReducer
        exclude = ('make', 'name', 'retailed')


class SoftwareEditForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Software
        exclude = ('make', 'name', 'retailed')


class FilterEditForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Filter
        exclude = ('make', 'name', 'retailed')


class AccessoryEditForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Accessory
        exclude = ('make', 'name', 'retailed')


class TelescopeEditNewForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Telescope
        fields = ('make', 'name')
        widgets = {
            'make': forms.TextInput(attrs = {'autocomplete': 'off'}),
            'name': forms.TextInput(attrs = {'autocomplete': 'off'}),
        }


class MountEditNewForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Mount
        fields = ('make', 'name')
        widgets = {
            'make': forms.TextInput(attrs = {'autocomplete': 'off'}),
            'name': forms.TextInput(attrs = {'autocomplete': 'off'}),
        }



class CameraEditNewForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Camera
        fields = ('make', 'name')
        widgets = {
            'make': forms.TextInput(attrs = {'autocomplete': 'off'}),
            'name': forms.TextInput(attrs = {'autocomplete': 'off'}),
        }



class FocalReducerEditNewForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = FocalReducer
        fields = ('make', 'name')
        widgets = {
            'make': forms.TextInput(attrs = {'autocomplete': 'off'}),
            'name': forms.TextInput(attrs = {'autocomplete': 'off'}),
        }



class SoftwareEditNewForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Software
        fields = ('make', 'name')
        widgets = {
            'make': forms.TextInput(attrs = {'autocomplete': 'off'}),
            'name': forms.TextInput(attrs = {'autocomplete': 'off'}),
        }



class FilterEditNewForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Filter
        fields = ('make', 'name')
        widgets = {
            'make': forms.TextInput(attrs = {'autocomplete': 'off'}),
            'name': forms.TextInput(attrs = {'autocomplete': 'off'}),
        }



class AccessoryEditNewForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Accessory
        fields = ('make', 'name')
        widgets = {
            'make': forms.TextInput(attrs = {'autocomplete': 'off'}),
            'name': forms.TextInput(attrs = {'autocomplete': 'off'}),
        }



class CopyGearForm(forms.Form):
    image = forms.ModelChoiceField(
        queryset = None,
    )

    def __init__(self, user, **kwargs):
        super(CopyGearForm, self).__init__(**kwargs)
        self.fields['image'].queryset = Image.objects.filter(user = user)


class AppApiKeyRequestForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = AppApiKeyRequest


class GearUserInfoForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = GearUserInfo


class ModeratorGearFixForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = Gear
        fields = ('make', 'name',)
        widgets = {
            'make': forms.TextInput(attrs = {
                'data-provide': 'typeahead',
                'data-source': simplejson.dumps(
                    uniq([x.make for x in Gear.objects.exclude(make = None).exclude(make = '')])),
                'autocomplete': 'off',
            }),
        }

    def clean_make(self):
        return self.cleaned_data['make'].strip()

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def save(self, force_insert = False, force_update = False, commit = True):
        instance = getattr(self, 'instance', None)
        old_make = Gear.objects.get(id = instance.id).make
        old_name = Gear.objects.get(id = instance.id).name

        m = super(ModeratorGearFixForm, self).save(commit = False)

        # Update the time
        m.moderator_fixed = datetime.datetime.now()

        if commit:
            m.save()

        return m


class ClaimCommercialGearForm(forms.Form):
    error_css_class = 'error'

    make = forms.ChoiceField(
        choices = [('', '---------')] + sorted(uniq(Gear.objects.exclude(make = None).exclude(make = '').values_list('make', 'make')), key = lambda x: x[0].lower()),
        label = _("Make"),
        help_text = _("The make, brand, producer or developer of this product."),
        required = True)

    name = forms.ChoiceField(
        choices = [('', '---------')],
        label = _("Name"),
        required = True)

    merge_with = forms.ChoiceField(
        choices = [('', '---------')],
        label = _("Merge"),
        help_text = _("Use this field to mark that the item you are claiming really is the same product (or a variation thereof) of something you have claimed before."),
        required = False)

    def __init__(self, user, **kwargs):
        super(ClaimCommercialGearForm, self).__init__(**kwargs)
        self.user = user
        self.fields['merge_with'].choices = [('', '---------')] + uniq(CommercialGear.objects.filter(producer = user).values_list('id', 'proper_name'))

    def clean (self):
        cleaned_data = super(ClaimCommercialGearForm, self).clean()

        max_items = affiliate_limit(self.user)
        current_items = CommercialGear.objects.filter(producer = self.user).count()
        if current_items >= max_items:
            raise forms.ValidationError(_("You can't create more than %d claims. Consider upgrading your affiliation!" % max_items))

        return self.cleaned_data


class MergeCommercialGearForm(forms.Form):
    error_css_class = 'error'

    merge_with = forms.ChoiceField(
        choices = [('', '---------')],
        label = _("Merge"),
        help_text = _("Use this field to mark that the item you are merging really is the same product (or a variation thereof) of something you have claimed before."),
        required = False)

    def __init__(self, user, **kwargs):
        super(MergeCommercialGearForm, self).__init__(**kwargs)
        self.fields['merge_with'].choices = [('', '---------')] + uniq(CommercialGear.objects.filter(producer = user).values_list('id', 'proper_name'))


class CommercialGearForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = CommercialGear

    def __init__(self, user, **kwargs):
        super(CommercialGearForm, self).__init__(**kwargs)
        self.fields['image'].queryset = Image.objects.filter(user = user, subject_type = 500)


class ClaimRetailedGearForm(forms.Form):
    error_css_class = 'error'

    make = forms.ChoiceField(
        choices = [('', '---------')] + sorted(uniq(Gear.objects.exclude(make = None).exclude(make = '').values_list('make', 'make')), key = lambda x: x[0].lower()),
        label = _("Make"),
        help_text = _("The make, brand, producer or developer of this product."),
        required = True)

    name = forms.ChoiceField(
        choices = [('', '---------')],
        label = _("Name"),
        required = True)

    merge_with = forms.ChoiceField(
        choices = [('', '---------')],
        label = _("Merge"),
        help_text = _("Use this field to mark that the item you are claiming really is the same product (or a variation thereof) of something you have claimed before."),
        required = False)

    def __init__(self, user, **kwargs):
        super(ClaimRetailedGearForm, self).__init__(**kwargs)
        self.user = user
        self.fields['merge_with'].choices =\
            [('', '---------')] +\
            uniq_id_tuple(RetailedGear.objects.filter(retailer = user).exclude(gear__name = None).values_list('id', 'gear__name'))

    def clean (self):
        cleaned_data = super(ClaimRetailedGearForm, self).clean()

        max_items = retailer_affiliate_limit(self.user)
        current_items = RetailedGear.objects.filter(gear = self.user).count()
        if current_items >= max_items:
            raise forms.ValidationError(_("You can't create more than %d claims. Consider upgrading your affiliation!" % max_items))

        already_claimed = set(
            item.id
                for sublist in [x.gear_set.all() for x in RetailedGear.objects.filter(retailer = self.user)]
            for item in sublist)

        if int(cleaned_data['name']) in already_claimed:
            raise forms.ValidationError(_("You have already claimed this product."))

        return self.cleaned_data


class MergeRetailedGearForm(forms.Form):
    error_css_class = 'error'

    merge_with = forms.ChoiceField(
        choices = [('', '---------')],
        label = _("Merge"),
        help_text = _("Use this field to mark that the item you are merging really is the same product (or a variation thereof) of something you have claimed before."),
        required = False)

    def __init__(self, user, **kwargs):
        super(MergeRetailedGearForm, self).__init__(**kwargs)
        self.fields['merge_with'].choices =\
            [('', '---------')] +\
            uniq_id_tuple(RetailedGear.objects.filter(retailer = user).exclude(gear__name = None).values_list('id', 'gear__name'))


class RetailedGearForm(forms.ModelForm):
    error_css_class = 'error'

    class Meta:
        model = RetailedGear
