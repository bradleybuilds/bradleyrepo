from slyguy import plugin
from slyguy.util import set_kodi_string
from slyguy.constants import IS_ANDROID, IS_PYTHON3, KODI_VERSION
from slyguy.settings import CommonSettings
from slyguy.settings.types import Bool, Browse, Text, Enum, Action

from .language import _


def set_trailer_context():
    value = ''
    if settings.TRAILER_CONTEXT.value:
        if settings.TRAILER_CONTEXT_MOVIES.value:
            value += '1,'
        if settings.TRAILER_CONTEXT_TV.value:
            value += '2,'
        if settings.TRAILER_CONTEXT_SEASONS.value:
            value += '3,'
    set_kodi_string('_slyguy_trailer_context_menu', value)


class YTMode:
    YOUTUBE_PLUGIN = 'youtube_plugin'
    TUBED_PLUGIN = 'tubed_plugin'
    APK = 'apk'
    YT_DLP = 'yt-dlp'


YT_OPTIONS = []
if IS_PYTHON3:
    YT_OPTIONS.append([_.YT_DLP, YTMode.YT_DLP])
if IS_ANDROID:
    YT_OPTIONS.append([_.YT_APK, YTMode.APK])
YT_OPTIONS.append([_.YOUTUBE_PLUGIN, YTMode.YOUTUBE_PLUGIN])
YT_OPTIONS.append([_.TUBED_PLUGIN, YTMode.TUBED_PLUGIN])


class Settings(CommonSettings):
    TRAILER_CONTEXT = Bool('trailer_context', _.TRAILER_CONTEXT, default=True, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context)
    TRAILER_CONTEXT_MOVIES = Bool('trailer_context_movies', _.TRAILER_CONTEXT_MOVIES, default=True, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context, parent=TRAILER_CONTEXT)
    TRAILER_CONTEXT_TV = Bool('trailer_context_tv', _.TRAILER_CONTEXT_TV, default=True, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context, parent=TRAILER_CONTEXT)
    TRAILER_CONTEXT_SEASONS = Bool('trailer_context_seasons', _.TRAILER_CONTEXT_SEASONS, default=True, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context, parent=TRAILER_CONTEXT)

    TRAILER_LOCAL = Bool('trailer_local', _.TRAILER_LOCAL, default=True, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context)
    IGNORE_SCRAPED = Bool('ignore_scraped', _.IGNORE_SCRAPED, default=False)
    MDBLIST_SEARCH = Bool('mdblist_search', _.TRAILER_SEARCH, default=True, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context)
    MDBLIST = Bool('mdblist', _.TRAILER_YOUTUBE, default=True, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context)
    TRAILER_IMDB = Bool('trailer_imdb', _.TRAILER_IMDB, default=False, after_save=lambda val:set_trailer_context(), after_clear=set_trailer_context)

    YT_PLAY_WITH = Enum('yt_play_with', _.YT_PLAY_WITH, options=YT_OPTIONS, default=YT_OPTIONS[0][1])

    YT_SUBTITLES = Bool('dlp_subtitles', _.YT_SUBTITLES, default=True, visible=lambda: settings.YT_PLAY_WITH.value == YTMode.YT_DLP, parent=YT_PLAY_WITH)
    YT_AUTO_SUBTITLES = Bool('dlp_auto_subtitles', _.YT_AUTO_SUBTITLES, default=True, visible=lambda: settings.YT_PLAY_WITH.value == YTMode.YT_DLP, parent=YT_PLAY_WITH)
    YT_COOKIES_PATH = Browse('dlp_cookies_path', _.YT_DLP_COOKIES_PATH, type=Browse.FILE, visible=lambda: settings.YT_PLAY_WITH.value == YTMode.YT_DLP, parent=YT_PLAY_WITH)
    YT_PLAY_FALLBACK = Enum('yt_play_fallback', _.YT_PLAY_FALLBACK, options=[x for x in YT_OPTIONS if x[1] != YTMode.YT_DLP], visible=lambda: settings.YT_PLAY_WITH.value == YTMode.YT_DLP, parent=YT_PLAY_WITH)
    YT_APK_ID = Text('yt_apk_id', _.YT_NATIVE_APK_ID, default_label=_.AUTO, visible=lambda: settings.YT_PLAY_WITH.value == YTMode.APK or settings.YT_PLAY_FALLBACK.value == YTMode.APK, parent=YT_PLAY_WITH)

    REVERSE_LOOKUP_MOVIE = Bool('reverse_lookup_movie', _.REVERSE_LOOKUP_MOVIE, default=True)
    REVERSE_LOOKUP_TVSHOW = Bool('reverse_lookup_tvshow', _.REVERSE_LOOKUP_TVSHOW, default=True, enable=KODI_VERSION >= 22, disabled_value=False, disabled_reason=_.REVERSE_LOOKUP_TVSHOW_KODI22)
    TESTSTREAMS = Action("Container.Update({})".format(plugin.url_for('/test_streams')), _.TEST_STREAMS)


settings = Settings()
