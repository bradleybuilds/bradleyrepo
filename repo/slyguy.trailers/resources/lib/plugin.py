import os
from difflib import SequenceMatcher

from kodi_six import xbmc, xbmcvfs
from six.moves.urllib_parse import urlparse

from slyguy import plugin, gui
from slyguy.constants import ROUTE_CONTEXT, ROUTE_SETTINGS, KODI_VERSION, ADDON_ID
from slyguy.log import log
from slyguy.util import get_addon, kodi_rpc, remove_kodi_formatting

from .settings import settings
from .youtube import play_youtube, get_youtube_id
from .mdblist import API
from .imdb import play_imdb
from .language import _
from .constants import SEARCH_MATCH_RATIO, TrailerItem

mdblist_api = API()


@plugin.route('/')
def home(**kwargs):
    return plugin.url_for(ROUTE_SETTINGS)


def _get_trailer_path(path):
    if not path:
        return ''

    video_id = get_youtube_id(path)
    if video_id:
        return plugin.url_for(play_yt, video_id=video_id, busy=0)
    else:
        return path


def _fetch_movie_info(movieid):
    try:
        return kodi_rpc('VideoLibrary.GetMovieDetails', {'movieid': int(movieid), 'properties': ['title', 'year', 'imdbnumber', 'uniqueid', 'file', 'trailer']})['moviedetails']
    except KeyError:
        log.warning("RPC failed to find movieid: {}".format(movieid))
        return

def _fetch_show_info(seasonid=None, tvshowid=None):
    if not seasonid and not tvshowid:
        return

    if not tvshowid:
        try:
            tvshowid = kodi_rpc('VideoLibrary.GetSeasonDetails', {'seasonid': int(seasonid), 'properties': ['tvshowid']})['seasondetails']['tvshowid']
        except KeyError:
            log.warning("RPC failed to find seasonid: {}".format(seasonid))
            return

    properties = ['title', 'year', 'imdbnumber', 'uniqueid', 'file']
    if KODI_VERSION >= 22:
        # Kodi 22 can also have trailer property
        properties.append('trailer')

    try:
        data = kodi_rpc('VideoLibrary.GetTVShowDetails', {'tvshowid': int(tvshowid), 'properties': properties})['tvshowdetails']
        if KODI_VERSION < 22:
            # downstream code expects trailer key
            data['trailer'] = ''
        return data
    except KeyError:
        log.warning("RPC failed to find tvshowid: {}".format(tvshowid))
        return


def _db_to_item(mediatype, dbid):
    dbid = int(dbid)
    if dbid < 0:
        return None

    if mediatype == 'movie':
        data = _fetch_movie_info(movieid=dbid)
        if data:
            return _rpc_to_item(data)
    elif mediatype == 'tvshow':
        data = _fetch_show_info(tvshowid=dbid)
        if data:
            return _rpc_to_item(data)

    return None


def _li_to_item(li):
    vid_tag = li.getVideoInfoTag()
    mediatype = vid_tag.getMediaType()
    dbid = int(vid_tag.getDbId())

    # prefer rpc items for scanned items as they return all unique ids etc
    item = _db_to_item(mediatype, dbid)
    if item:
        # Kodi before 22 dont have trailer for show, add our vid_tag trailer
        if not item.info['trailer']:
            item.info['trailer'] = vid_tag.getTrailer()
        return item

    title = vid_tag.getTitle() or li.getLabel()
    if mediatype == 'season':
        title = vid_tag.getTVShowTitle()

    clean_title = remove_kodi_formatting(title)
    title = u"{} ({})".format(clean_title, _.TRAILER)

    item = TrailerItem()
    item.label = title
    item.info = {
        'dbid': dbid,
        'mediatype': mediatype,
        'title': title,
        'season_number': -1,
        'plot': vid_tag.getPlot(),
        'tagline': vid_tag.getTagLine(),
        'trailer': vid_tag.getTrailer(),
        'year': vid_tag.getYear(),
    }
    item.data = {
        'fallback': None,
        'dir': None,
        'filename': None,
        'clean_title': clean_title,
        'unique_id': {},
    }

    if mediatype == 'season':
        item.info['mediatype'] = 'tvshow'
        show_data = None

        # season often has the year of the season which causes search to fail
        # grab the year and show title of our show if we are DB media
        if vid_tag.getSeason() < 0:
            # All seasons - cant query season. Kodi 19 allows getting TvShowDBID info label
            if KODI_VERSION >= 19:
                show_data = _fetch_show_info(tvshowid=xbmc.getInfoLabel('ListItem.TvShowDBID'))
                if show_data:
                    # no season so use our shows trailer as our own if available
                    item.info['trailer'] = show_data.get('trailer')
        else:
            item.info['season_number'] = vid_tag.getSeason()
            show_data = _fetch_show_info(seasonid=vid_tag.getDbId())

        if show_data:
            item.info['title'] = show_data['title']
            item.info['year'] = show_data['year']
            item.data['fallback'] = show_data.get('trailer') # TODO: support fallback

    if item.info['mediatype'] == 'movie':
        path = vid_tag.getFilenameAndPath()
        item.data['dir'] = os.path.dirname(path)
        item.data['filename'] = os.path.basename(path)
    elif item.info['mediatype'] == 'tvshow':
        item.data['dir'] = os.path.dirname(vid_tag.getPath())

    for key in ['thumb','poster','banner','fanart','clearart','clearlogo','landscape','icon']:
        item.art[key] = li.getArt(key)

    # try our best to get the imdbid
    if KODI_VERSION >= 20:
        item.info['genre'] = vid_tag.getGenres()
        for id_type in ('imdb', 'tvdb', 'tmdb'):
            # getUniqueID on context on db content only returns its main id :(
            # but we now use rpc for those so OK
            unique_id = vid_tag.getUniqueID(id_type)
            if unique_id:
                item.data['unique_id'] = {'type': id_type, 'id': unique_id}
                break
    else:
        item.info['genre'] = vid_tag.getGenre()

    if not item.data['unique_id'].get('type') == 'imdb':
        id = vid_tag.getIMDBNumber() or ''
        id_type = 'imdb' if id.lower().startswith('tt') else None
        if id_type or not item.data['unique_id']:
            item.data['unique_id'] = {'type': id_type, 'id': id}

    return item


def _rpc_to_item(data):
    clean_title = remove_kodi_formatting(data.get('title') or data.get('label'))
    title = u"{} ({})".format(clean_title, _.TRAILER)

    item = TrailerItem()
    item.label = title
    item.info = {
        'dbid': data['movieid'] if 'movieid' in data else data['tvshowid'],
        'mediatype': 'movie' if 'movieid' in data else 'tvshow',
        'title': title,
        'season_number': -1,
        'trailer': data['trailer'],
        'year': data['year'],
    }
    item.data = {
        'fallback': None,
        'dir': None,
        'filename': None,
        'clean_title': clean_title,
        'unique_id': {},
    }

    if item.info['mediatype'] == 'movie':
        path = data['file']
        item.data['dir'] = os.path.dirname(path)
        item.data['filename'] = os.path.basename(path)
    elif item.info['mediatype'] == 'tvshow':
        item.data['dir'] = os.path.dirname(data['file'])

    # try best to get imdbidb
    for id_type in ('imdb', 'tmdb', 'tvdb'):
        unique_id = data.get('uniqueid', {}).get(id_type)
        if unique_id:
            item.data['unique_id'] = {'type': id_type, 'id': unique_id}
            break

    if not item.data['unique_id'].get('type') == 'imdb':
        id = data.get('imdbnumber') or ''
        id_type = 'imdb' if id.lower().startswith('tt') else None
        if id_type or not item.data['unique_id']:
            item.data['unique_id'] = {'type': id_type, 'id': id}

    return item


@plugin.route('/redirect')
def redirect(url, **kwargs):
    parsed = urlparse(url)
    if parsed.path.lower() in ('/search', '/kodion/search/query'):
        log.warning("SlyGuy Trailers does not support Youtube search ({}). Returning empty result".format(url))
        return plugin.Folder(no_items_label=None, show_news=False)

    log.debug("Reverse lookup for: '{}'".format(url))
    matches = _reverse_lookup_trailer(url)
    # TODO: how to handle multiple items with same trailer url?
    if len(matches) != 1:
        log.info("{} matches found from reverse lookup. Fallback to YT trailer".format(len(matches)))
        video_id = get_youtube_id(url)
        return play_youtube(video_id=video_id)

    log.info("Found match from reverse lookup: {}".format(matches[0].data['clean_title']))
    item = _process_item(matches[0])
    if ADDON_ID in item.path:
        return plugin.redirect(item.path)
    else:
        return item


@plugin.route(ROUTE_CONTEXT)
def context_trailer(listitem, **kwargs):
    with gui.busy():
        item = _li_to_item(listitem)
        return _process_item(item)


def _require_addon(url):
    parsed = urlparse(url)
    if parsed.scheme.lower() == 'plugin' and parsed.netloc != ADDON_ID:
        get_addon(parsed.netloc, install=True, required=True)


def _process_item(item):
    log.debug('Process item: {}'.format(item.info))

    # check local trailer first
    if settings.TRAILER_LOCAL.value:
        item.path = _get_local_trailer(
            mediatype = item.info['mediatype'],
            dir = item.data['dir'],
            filename = item.data['filename'],
        )
        if item.path:
            _require_addon(item.path)
            return item

    # scraped trailer
    if not settings.IGNORE_SCRAPED.value:
        item.path = _get_trailer_path(path=item.info['trailer'])
        if item.path:
            _require_addon(item.path)
            return item

    # if no unique id, try mdblist search by title/year
    if not item.data['unique_id'].get('id') and settings.MDBLIST_SEARCH.value:
        item.data['unique_id'] = _search_mdblist_for_id(
            mediatype = item.info['mediatype'],
            title = item.data['clean_title'],
            year = item.info['year'],
        ) or {}

    # mdblist YouTube trailer
    if settings.MDBLIST.value:
        item.path = _get_mdblist_trailer(
            mediatype = item.info['mediatype'],
            id = item.data['unique_id'].get('id'),
            id_type = item.data['unique_id'].get('type'),
        )
        if item.path:
            return item

    # IMDB trailer
    if settings.TRAILER_IMDB.value:
        item.path = _get_imdb_trailer(
            mediatype = item.info['mediatype'],
            id = item.data['unique_id'].get('id'),
            id_type = item.data['unique_id'].get('type'),
            season_number = item.info['season_number'],
        )
        if item.path:
            return item

    gui.notification(_.TRAILER_NOT_FOUND)
    item.path = ''
    return item


def _reverse_lookup_trailer(trailer):
    if not trailer:
        return []

    trailer = trailer.lower()
    results = []
    if settings.REVERSE_LOOKUP_MOVIE.value:
        rows = kodi_rpc('VideoLibrary.GetMovies', {'filter': {'field': 'hastrailer', 'operator': 'true', 'value': '1'}, 'properties': ['trailer']})['movies']
        for row in rows:
            if trailer in row["trailer"].lower():
                results.append(_fetch_movie_info(row['movieid']))

    if not results and settings.REVERSE_LOOKUP_TVSHOW.value:
        rows = kodi_rpc('VideoLibrary.GetTvShows', {'filter': {'field': 'hastrailer', 'operator': 'true', 'value': '1'}, 'properties': ['trailer']})['tvshows']
        for row in rows:
            if trailer in row["trailer"].lower():
                results.append(_fetch_show_info(row['tvshowid'])['tvshowdetails'])

    return [_rpc_to_item(result) for result in results if result]


def _get_local_trailer(mediatype, dir, filename):
    if mediatype == 'movie' and filename:
        filename = os.path.splitext(filename)[0].lower()
        files = xbmcvfs.listdir(dir)[1]
        for file in files:
            name, ext = os.path.splitext(file.lower())
            if name in ('movie-trailer', "{}-trailer".format(filename)):
                path = os.path.join(dir, file)
                if ext == '.txt':
                    with xbmcvfs.File(path) as f:
                        path = _get_trailer_path(f.read().strip())
                return path

    elif mediatype == 'tvshow' and dir:
        folder_name = os.path.basename(dir).lower()
        files = xbmcvfs.listdir(dir)[1]
        for file in files:
            name, ext = os.path.splitext(file.lower())
            if name in ('tvshow-trailer', "{}-trailer".format(folder_name)):
                path = os.path.join(dir, file)
                if ext == '.txt':
                    with xbmcvfs.File(path) as f:
                        path = _get_trailer_path(f.read().strip())
                return path


def _get_imdb_trailer(mediatype, id, id_type, season_number):
    if not mediatype or not id:
        return

    if id_type != 'imdb':
        try:
            imdb_id = mdblist_api.get_media(mediatype, id, id_type)['ids']['imdb']
        except KeyError:
            return
    else:
        imdb_id = id

    return plugin.url_for(imdb, video_id=imdb_id, season_number=season_number, busy=0)


def _search_mdblist_for_id(mediatype, title, year):
    if not mediatype or not title or not year:
        return

    log.debug("mdblist search for: {} '{}' ({})".format(mediatype, title, year))
    results = mdblist_api.search_media(mediatype, title, year, limit=10)
    title = "{} {}".format(title.lower().strip().replace(' ', ''), year)
    for result in results:
        result['ratio'] = SequenceMatcher(None, title, "{} {}".format(result['title'].lower().strip().replace(' ', ''), result['year'])).ratio()
    results = sorted(results, key=lambda x: x['ratio'], reverse=True)
    log.debug("mdblist search results: {}".format(results))

    results = [x for x in results if x['ratio'] >= SEARCH_MATCH_RATIO]
    if not results:
        return

    log.info("mdblist search result: {}".format(results[0]))
    if not results[0].get('ids'):
        return

    for id_type in ('imdb', 'tvdb', 'tmdb'):
        id = results[0]['ids'].get(id_type) or results[0]['ids'].get(id_type+'id')
        if id:
            return {'type': id_type, 'id': id}


def _get_mdblist_trailer(mediatype, id, id_type):
    if not mediatype or not id:
        return

    data = mdblist_api.get_media(mediatype, id, id_type=id_type)
    trailer = _get_trailer_path(data.get('trailer'))
    if ADDON_ID in trailer:
        log.info("mdblist trailer: {}".format(trailer))
        return trailer


@plugin.route('/by_dbid')
def by_dbid(mediatype, dbid, fallback='', **kwargs):
    item = _db_to_item(mediatype, dbid)
    if fallback and not item.info['trailer']:
        item.info['trailer'] = fallback
    with gui.busy():
        return _process_item(item)


@plugin.route('/by_unique_id')
def by_unique_id(mediatype, id, id_type=None, **kwargs):
    item = TrailerItem()
    item.label = ''
    item.info = {
        'title': '',
        'trailer': '',
        'season_number': -1,
        'year': '',
        'mediatype': mediatype,
    }
    item.data = {
        'fallback': None,
        'dir': None,
        'filename': None,
        'clean_title': '',
        'unique_id': {'type': id_type, 'id': id},
    }
    with gui.busy():
        return _process_item(item)


@plugin.route('/by_title_year')
def by_title_year(mediatype, title, year, **kwargs):
    item = TrailerItem()
    item.label = title
    item.info = {
        'title': title,
        'trailer': '',
        'season_number': -1,
        'year': year,
        'mediatype': mediatype,
    }
    item.data = {
        'fallback': None,
        'dir': None,
        'filename': None,
        'clean_title': title,
        'unique_id': {},
    }
    with gui.busy():
        return _process_item(item)


@plugin.route('/play')
def play_yt(video_id, busy=1, **kwargs):
    with gui.busy(busy):
        return play_youtube(video_id)


@plugin.route('/imdb')
def imdb(video_id, season_number=-1, busy=1, **kwargs):
    with gui.busy(busy):
        return play_imdb(video_id, season_number=season_number)


@plugin.route('/test_streams')
def test_streams(**kwargs):
    STREAMS = [
        ['YouTube 4K', plugin.url_for(play_yt, video_id='Q82tQJyJwgk')],
        ['YouTube 4K HDR', plugin.url_for(play_yt, video_id='tO01J-M3g0U')],
        ['IMDB', plugin.url_for(imdb, video_id='tt10548174')],
        ['Movie imdb id -> mdblist', plugin.url_for(by_unique_id, mediatype='movie', id='tt0133093', id_type='imdb')],
        ['Movie Title / Year -> mdblist', plugin.url_for(by_title_year, mediatype='movie', title='The Matrix', year='1999')],
        ['Show tvdb id -> mdblist', plugin.url_for(by_unique_id, mediatype='tvshow', id='392256', id_type='tvdb')],
        ['Show Title / Year -> mdblist', plugin.url_for(by_title_year, mediatype='tvshow', title='The Last of Us', year='2023')],
    ]

    folder = plugin.Folder(_.TEST_STREAMS, content=None)
    for stream in STREAMS:
        folder.add_item(label=stream[0], is_folder=False, path=stream[1])
    return folder
