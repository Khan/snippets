"""Snippets server -> HipChat integration.

At Khan Academy we use HipChat for messaging.  This provides HipChat
integration with the snippet server.

Talking to the Khan HipChat 'rooms' requires a token.  The admin must
set this token by creating a file called 'hipchat.cfg' in this
directory.  It should look like this:
--- vvv contents below vvv---
token = 01234567890abcdef
--- ^^^ contents above ^^^---
except instead of '01234567890abcdef', it should have the token value.
For Khan Academy, this is stored in secrets.py.

Note that there are no quotes, and there must be spaces around the =,
or this won't work.

Do not commit hipchat.cfg into git!  It's a secret.
"""

import logging
import urllib
import urllib2

from google.appengine.ext import webapp


_TOKEN = None


def hipchat_init():
    """Initializes hipchat, returns true if it worked ok."""
    global _TOKEN
    config_fname = 'hipchat.cfg'
    try:
        config = open(config_fname).read().strip()
        if not config.startswith('token = '):
            raise ValueError('%s should look like "token = <value>\n"')
        _TOKEN = config[len('token = '):]
        return True
    except IOError:
        logging.error('Unable to open %s; disabling HipChat' % config_fname)
        return False
    except ValueError, why:
        logging.error('%s; disabling HipChat' % why)
        return False


def _make_hipchat_api_call(post_dict_with_secret_token):
    # This is a separate function just to make it easy to mock for tests.
    r = urllib2.urlopen('https://api.hipchat.com/v1/rooms/message',
                        urllib.urlencode(post_dict_with_secret_token))
    if r.getcode() != 200:
        raise ValueError(r.read())


def send_to_hipchat_room(room_name, message):
    """Assuming hipchat_init() was called previously, send message to room."""
    # urlencode requires that all fields be in utf-8.
    post_dict = {
        'room_id': room_name.encode('utf-8'),
        'from': 'snippet-server',
        'notify': 1,
        'message': message.encode('utf-8'),
        'auth_token': _TOKEN,
    }

    if not _TOKEN:
        logging.warning("Not sending this to hipchat (no token found): %s"
                        % post_dict)
    else:
        try:
            _make_hipchat_api_call(post_dict)
        except Exception, why:
            del post_dict['auth_token']     # don't log the secret token!
            logging.error('Failed sending %s to hipchat: %s'
                          % (post_dict, why))


class TestSendToHipchat(webapp.RequestHandler):
    """Send a (fixed) message to the hipchat room."""
    def get(self):
        send_to_hipchat_room('HipChat Tests', 'Test of snippets-to-hipchat')
        self.response.out.write('OK')
