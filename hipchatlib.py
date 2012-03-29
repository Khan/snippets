import hipchat.config
import hipchat.room

from google.appengine.ext import db
from google.appengine.ext import webapp

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

def hipchat_init():
    """Initializes hipchat, returns true if it worked ok."""
    hipchat.config.init_cfg('hipchat.cfg')
    return bool(hipchat.config.token)


def send_to_hipchat_room(room_name, message):
    """For this to work, the hipchat token must be in hipchat.cfg."""
    for room in hipchat.room.Room.list():
        if room.name == room_name:
            # Have to go through hoops since 'from' is reserved in python.
            msg_dict = {
                'room_id': room.room_id,
                'from': 'snippet-server',
                'notify': 1,
                'message': message,
            }
            hipchat.room.Room.message(**msg_dict)
            return
    raise RuntimeError('Unable to send message to hipchat room %s' % room_name)


class TestSendToHipchat(webapp.RequestHandler):
    """Send a (fixed) message to the hipchat room."""
    def get(self):
        send_to_hipchat_room('1s and 0s', 'Test of snippets-to-hipchat')
        self.response.out.write('OK')
