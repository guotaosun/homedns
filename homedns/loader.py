#!/usr/bin/env python
# -*- encoding:utf-8 -*-
# load from local or remote

import logging
import base64
import os
import os.path
import time
try:
    from urlparse import urlparse
    from urllib2 import urlopen, Request, build_opener
    from StringIO import StringIO
except:
    from urllib.parse import urlparse
    from urllib.request import urlopen, Request, build_opener
    from io import StringIO

import socks
from sockshandler import SocksiPyHandler

from . import globalvars


logger = logging.getLogger(__name__)


class BaseLoader(object):
    def __init__(self, url, proxy=None):
        bname = os.path.basename(url)
        if bname == url:
            self.url = os.path.join(globalvars.config_dir, bname)
        else:
            self.url = url
        cache_dir = os.path.join(globalvars.config_dir, 'cache')
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        self.cache = os.path.join(cache_dir, bname)
        self.proxy = proxy

        parser = urlparse(self.url)
        self.local = not parser.netloc
        self._last_update_time = 0

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, self.url)

    def is_base64(self, data):
        if not isinstance(data, str):
            data = data.decode('utf-8')
        lines = data.strip().split('\n')
        nums = list(map(len, lines))
        for x in range(len(nums) - 1):
            if nums[x] != 64:
                return False
        if nums[-1] % 4 != 0:
            return False
        if not lines[-1][0].isalnum():
            return False
        if '.' in lines[-1]:
            return False
        return True

    def open(self, proxy=None, cache=True):
        if self.local:
            self._last_update_time = os.stat(self.url).st_mtime
            return open(self.url)
        elif cache and os.path.exists(self.cache):
            self._last_update_time = os.stat(self.cache).st_mtime
            return open(self.cache)
        else:
            r = Request(self.url)
            if proxy or self.proxy:
                proxy = proxy if proxy else self.proxy
                opener = build_opener(SocksiPyHandler(
                    socks.PROXY_TYPES[proxy['type'].upper()],
                    proxy['ip'],
                    proxy['port'],
                ))
                data_io = opener.open(r)
            else:
                data_io = urlopen(r)
            data = data_io.read()
            if self.is_base64(data):
                logger.debug('BASE64 decode...')
                data = base64.b64decode(data)
            if not isinstance(data, str):
                data = data.decode('utf-8')
            if self.cache:
                with open(self.cache, 'w') as f:
                    f.write(data)
                self._last_update_time = os.stat(self.cache).st_mtime
                return open(self.cache)
            self._last_update_time = time.time()
            return StringIO(data)

    def lastUpdateTime(self):
        return self._last_update_time

    def isNeedUpdate(self, refresh):
        if self.local:
            return self.lastUpdateTime() != os.stat(self.url).st_mtime
        else:
            t = time.time()
            return t > (self.lastUpdateTime() + refresh)


class TxtLoader(BaseLoader):
    pass


class JsonLoader(BaseLoader):
    pass


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('url', help='load url or path')
    args = parser.parse_args()

    globalvars.init()
    globalvars.config_dir = ''
    loader = TxtLoader(args.url)
    data = loader.open().read()
    print(data)
