"""
fuo_dl
------
fuo_dl 是 FeelUOwn 的一个音乐下载插件。

fuo_dl 支持多首歌并行下载，也支持一首歌分多段并行下载（也就是常说的多线程下载）。
另外，用户可以在 ~/.fuorc 中自定义下载路径::

   config.DOWNLOAD_DIR = '~/Music'
"""

import logging
import os
from concurrent.futures import wait

from .downloader import Downloader as DownloaderBase
from .progress import ConsoleProgress
DOWNLOAD_DIR = os.path.expanduser('~') + '/Desktop/songs'
AUDIO_DOWNLOAD_POLICY = 'hq<>'

__alias__ = '音乐下载'
__desc__ = __doc__
__version__ = '0.1'


logger = logging.getLogger(__name__)


# TODO: prepare_url/prepare_filename shouldn't be here
def cook_tagobj(song):
    def beautify_str(str):
        return str.replace(' （', ' (').replace('（', ' (').replace('）', ')').strip()

    tag_obj = {
        'title': song.title,
        'artist': song.artists_name
    }
    if song.album_name.strip():
        tag_obj['album'] = song.album_name
        tag_obj['albumartist'] = song.album.artists_name
        cover_url = song.album.cover

        if hasattr(song.album, '_more_info'):
            album_info = song.album._more_info()
            if int(song.identifier) in album_info['discs']:
                tag_obj['discnumber'] = album_info.pop('discs')[int(song.identifier)]
                tag_obj['tracknumber'] = album_info.pop('tracks')[int(song.identifier)]
            else:
                album_info.pop('discs')
                album_info.pop('tracks')
            tag_obj = dict(tag_obj, **album_info)
    else:
        cover_url = song.artists[0].cover

    for key in tag_obj.keys():
        try:
            import inlp.convert.chinese as cv
        except Exception as e:
            logger.warning(e)
            tag_obj[key] = beautify_str(tag_obj[key])
        else:
            tag_obj[key] = cv.s2t(beautify_str(tag_obj[key]))
    return tag_obj, cover_url


def cook_filepath(tag_obj, ext):
    def correct_str(str):
        return str.replace('/', '_').replace(':', '_')

    if tag_obj.get('album'):
        storage_path = '{}/{}'.format(correct_str(tag_obj['albumartist']), correct_str(tag_obj['album']))
        extra_name = ''
        if tag_obj.get('discnumber') and tag_obj.get('tracknumber'):
            extra_name = '{:0>2d} '.format(int(tag_obj['tracknumber'].split('/')[0]))
            if len(tag_obj['discnumber'].split('/')) > 1 and int(tag_obj['discnumber'].split('/')[1]) > 1:
                extra_name = '{}-{}'.format(tag_obj['discnumber'].split('/')[0], extra_name)
        filename = '{}{}.{}'.format(extra_name, correct_str(tag_obj['title']), ext)
    else:
        storage_path = correct_str(tag_obj['artist'])
        filename = '{}.{}'.format(correct_str(tag_obj['title']), ext)
    return storage_path, filename


def prepare_url(song, app):
    if song.meta.support_multi_quality:
        media, _ = song.select_media(AUDIO_DOWNLOAD_POLICY)
        url = media.url
        ext = media.metadata.format
    else:
        url = song.url
        ext = url.split('?')[0].split('.')[-1] if '?' in url else 'mp3'

    if not url:
        songs = app.library.list_song_standby(song)
        if songs:
            song = songs[0]
        logger.warning('url source turns to {}: {}-{}-{}-{}'.format(
            song.source, song.title, song.artists_name, song.album_name, song.duration_ms))
        url, ext = prepare_url(song)

    return url, ext


def prepare_filename(song, ext, app):
    tag_obj, cover_url = cook_tagobj(song)
    storage_path, filename = cook_filepath(tag_obj, ext)

    absolute_path = '{}/{}'.format(DOWNLOAD_DIR, storage_path)
    if not os.path.isdir(absolute_path):
        os.makedirs(absolute_path)
    absolute_name = '{}/{}'.format(absolute_path, filename)
    return absolute_name, tag_obj, cover_url


def download(url, filename, console=False):
    dler = DownloaderBase()
    progress_cb = None
    if console is True:
        progress_cb = ConsoleProgress().on_update
    return dler.create_task(url, filename, progress_cb=progress_cb)


from .tagger import set_tag_obj


class Downloader(object):

    instance = None

    def __init__(self, app):
        self._app = app

        if self._app.mode & self._app.GuiMode:
            self._app.ui.pc_panel.download_btn.clicked.connect(self.download_song)
        Downloader.instance = self

    def download_song(self):
        song = self._app.player.current_song
        if not song:
            logger.warning('Current song is invalid')
            return

        download_url, ext = prepare_url(song, self._app)
        if not download_url or os.path.exists(download_url):
            logger.warning('Request url is invalid')
            return

        filename, tag_obj, cover_url = prepare_filename(song, ext, self._app)

        download_task = download(download_url, filename)
        download_task.add_done_callback(lambda _: set_tag_obj(filename, tag_obj, cover_url))


def enable(app):
    downloader = Downloader(app)


def disable(app):
    if app.mode & app.GuiMode:
        app.ui.pc_panel.download_btn.clicked.disconnect()
