import sys

from urllib import urlencode
from urllib2 import urlopen, Request

if sys.version_info[0] == 2 and sys.version_info[1] < 6:
    import simplejson as json
else:
    import json

import hipchat.config

def partial(func, *args, **keywords):
    def newfunc(*fargs, **fkeywords):
        newkeywords = keywords.copy()
        newkeywords.update(fkeywords)
        return func(*(args + fargs), **newkeywords)
    newfunc.func = func
    newfunc.args = args
    newfunc.keywords = keywords
    return newfunc


def call_hipchat(cls, ReturnType, url, data=True, **kw):
    auth = [('format', 'json'), ('auth_token', hipchat.config.token)]
    if not data:
        auth.extend(kw.items())
    req = Request(url=url + '?%s' % urlencode(auth))
    if data:
        req.add_data(urlencode(kw.items()))
    if hipchat.config.proxy_server and hipchat.config.proxy_type:
        req.set_proxy(hipchat.config.proxy_server, hipchat.config.proxy_type)
    return ReturnType(json.load(urlopen(req)))


class HipChatObject(object):
    def __init__(self, jsono):
        self.jsono = jsono
        for k, v in jsono[self.sort].iteritems():
            setattr(self, k, v)

    def __str__(self):
        return json.dumps(self.jsono)

    def get_json(self):
        return self.jsono
