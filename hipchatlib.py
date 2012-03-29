import hipchat.connection
import hipchat.room

from google.appengine.ext import db

"""Snippets server -> HipChat integration.

At Khan Academy we use HipChat for messaging.  This provides HipChat
integration with the snippet server.

Talking to the Khan HipChat 'rooms' requires a token.  The admin must
set this token manually in the snippets datastore.  There is no API
for setting it.  For KA, the HipChat token lives in secrets.py.
"""

class HipchatToken(db.Model):
    """Where we store the private key used to communicate with hipchat.

    There is no API for setting the token -- you must go through the
    appengine admin console to do that.
    """
    token = db.StringProperty(default='')


def send_to_hipchat_room(room_name, message):
    """For this to work, the token must be stored manually in the datastore."""
    q = HipchatToken.all()
    hipchat.connection.token = q.get()
    room_name = 'ReviewBoard: csilvers' #!!
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


