"""Snippets server -> HipChat integration.

At Khan Academy we use HipChat for messaging.  This provides HipChat
integration with the snippet server.

Talking to the HipChat 'rooms' requires a token.  The admin must enter
the value of this token on /admin/settings.  There are instructions
there for how to do so.
"""

import logging
import urllib
import urllib2

from google.appengine.ext import webapp

import models


def _make_hipchat_api_call(post_dict_with_secret_token):
    # This is a separate function just to make it easy to mock for tests.
    r = urllib2.urlopen('https://api.hipchat.com/v1/rooms/message',
                        urllib.urlencode(post_dict_with_secret_token))
    if r.getcode() != 200:
        raise ValueError(r.read())


def send_to_hipchat_room(room_name, message):
    """Send message to room.  Token is taken from AppSettings.hipchat_token."""
    if not room_name:
        return

    try:
        app_settings = models.AppSettings.get().hipchat_token
    except ValueError:
        logging.warning('Not sending to HipChat: app settings not configured')
        return

    token = app_settings.hipchat_token
    if not token:
        # The token should always be set if the room-name is set.
        logging.error('Not sending to HipChat: no hipchat token set in '
                      '/admin/settings')
        return

    # urlencode requires that all fields be in utf-8.
    post_dict = {
        'room_id': room_name.encode('utf-8'),
        'from': 'snippet-server',
        'notify': 1,
        'message': message.encode('utf-8'),
        'auth_token': token,
    }

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
