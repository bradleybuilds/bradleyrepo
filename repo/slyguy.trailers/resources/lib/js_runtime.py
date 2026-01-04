import os
import re
import zipfile
import tarfile
import shutil

from slyguy import dialog
from slyguy.log import log
from slyguy.constants import ADDON_PROFILE
from slyguy.util import get_system_arch, xz_extract, gzip_extract, CHUNK_SIZE
from slyguy.session import Session

from .language import _


old_dir = os.path.join(ADDON_PROFILE, 'deno')
if os.path.exists(old_dir):
    shutil.rmtree(old_dir)

DEST_DIR = os.path.join(ADDON_PROFILE, 'js_runtime')
if not os.path.exists(DEST_DIR):
    os.makedirs(DEST_DIR)


def clear_dir():
    for file in os.listdir(DEST_DIR):
        os.remove(os.path.join(DEST_DIR, file))    


def install_deno(reinstall=False):
    VERSION = '2.5.6'

    SOURCES = {
        'Windows64bit': 'https://github.com/denoland/deno/releases/download/v{}/deno-x86_64-pc-windows-msvc.zip'.format(VERSION),
        'Linuxx86_64': 'https://github.com/denoland/deno/releases/download/v{}/deno-x86_64-unknown-linux-gnu.zip'.format(VERSION),
        'Linuxarm64': 'https://github.com/denoland/deno/releases/download/v{}/deno-aarch64-unknown-linux-gnu.zip'.format(VERSION),
        'Darwinx86_64': 'https://github.com/denoland/deno/releases/download/v{}/deno-x86_64-apple-darwin.zip'.format(VERSION),
        'Darwinarm64': 'https://github.com/denoland/deno/releases/download/v{}/deno-aarch64-apple-darwin.zip'.format(VERSION),
    }

    system, arch = get_system_arch()
    url = SOURCES.get(system + arch)
    if not url:
        log.info("Deno for {} {} not yet supported. Fallback to legacy built-in js extractor".format(system, arch))
        return None

    if system == "Windows":
        extension = '.exe'
    else:
        extension = ''

    dst_file = os.path.join(DEST_DIR, 'deno_' + VERSION + extension)
    if os.path.exists(dst_file) and not reinstall:
        log.debug("Found deno: {}".format(dst_file))
        return dst_file

    with dialog.progress(_(_.IA_DOWNLOADING_FILE, url=url), percent=50):
        # clear out old
        clear_dir()

        # download and extract
        Session().chunked_dl(url, dst_file+'.zip')
        with zipfile.ZipFile(dst_file+'.zip', "r") as z:
            z.extractall(DEST_DIR)

        os.remove(dst_file+'.zip')
        os.rename(os.path.join(DEST_DIR, os.listdir(DEST_DIR)[0]), dst_file)
        os.chmod(dst_file, 0o775)

    log.debug("Deno installed: {}".format(dst_file))
    return dst_file


def install_node(reinstall=False):
    SOURCES = {
        'Windows64bit': 'https://nodejs.org/dist/v25.2.1/node-v25.2.1-win-x64.zip',
        'Windows32bit': 'https://nodejs.org/dist/v22.21.1/node-v22.21.1-win-x86.zip',
        'Windowsarm64': 'https://nodejs.org/dist/v25.2.1/node-v25.2.1-win-arm64.zip',
        'Linuxx86_64': 'https://nodejs.org/dist/v25.2.1/node-v25.2.1-linux-x64.tar.xz',
        'Linuxarm64': 'https://nodejs.org/dist/v25.2.1/node-v25.2.1-linux-arm64.tar.xz',
        'Linuxarmv7': 'https://nodejs.org/dist/v22.21.1/node-v22.21.1-linux-armv7l.tar.xz',
        'Darwinx86_64': 'https://nodejs.org/dist/v25.2.1/node-v25.2.1-darwin-x64.tar.gz',
        'Darwinarm64': 'https://nodejs.org/dist/v25.2.1/node-v25.2.1-darwin-arm64.tar.gz',
        #'Androidarm64': 'https://packages.termux.dev/apt/termux-main/pool/main/n/nodejs/nodejs_24.9.0_aarch64.deb',
        #'Androidarmv7': 'https://packages.termux.dev/apt/termux-main/pool/main/n/nodejs/nodejs_24.9.0_arm.deb',
    }

    system, arch = get_system_arch()
    url = SOURCES.get(system + arch)
    if not url:
        log.info("nodejs for {} {} not yet supported. Fallback to legacy built-in js extractor".format(system, arch))
        return None

    version = re.search(r'v(\d+\.\d+\.\d+)', url).group(1)

    if system == "Windows":
        extension = '.exe'
    else:
        extension = ''

    dst_file = os.path.join(DEST_DIR, 'node-v{version}-{system}-{arch}{extension}'.format(system=system.lower(), arch=arch.lower(), version=version, extension=extension))
    if os.path.exists(dst_file) and not reinstall:
        log.debug("Found nodejs: {}".format(dst_file))
        return dst_file

    with dialog.progress(_(_.IA_DOWNLOADING_FILE, url=url), percent=50):
        clear_dir()

        filename = os.path.basename(url)
        name, ext = os.path.splitext(filename)
        dst_dl = os.path.join(DEST_DIR, filename)

        # download and extract
        Session().chunked_dl(url, dst_dl)

        if ext in ('.gz','.xz'):
            if ext == '.xz':
                xz_extract(dst_dl)
            else:
                gzip_extract(dst_dl)

            with tarfile.open(dst_dl, "r") as z:
                for member in z.getmembers():
                    if member.isfile() and member.name.lower().endswith('/bin/node'):
                        with z.extractfile(member) as f_in, open(dst_file, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out, length=CHUNK_SIZE)
                        break
                else:
                    raise Exception('not found')
        elif ext == '.zip':
            with zipfile.ZipFile(dst_dl, "r") as z:
                for name in z.namelist():
                    if os.path.basename(name).lower() == 'node.exe':
                        with z.open(name) as src, open(dst_file, "wb") as dst:
                            while True:
                                chunk = src.read(64 * 1024)
                                if not chunk:
                                    break
                                dst.write(chunk)
                        break
                else:
                    raise Exception('not found')
        else:
            raise Exception("unsupported url")

        os.remove(dst_dl)
        os.chmod(dst_file, 0o775)

    log.debug("nodejs installed: {}".format(dst_file))
    return dst_file


def install_js(reinstall=False):
    path = install_node(reinstall=reinstall)
    if path:
        return {'node': {'path': path}}
