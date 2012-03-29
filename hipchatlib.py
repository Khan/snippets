import hipchat.connection
import hipchat.room

from google.appengine.ext import db
from google.appengine.ext import webapp

"""Snippets server -> HipChat integration.

At Khan Academy we use HipChat for messaging.  This provides HipChat
integration with the snippet server.

Talking to the Khan HipChat 'rooms' requires a token.  The admin must
set this token manually in the snippets datastore, by visiting.  There is no API
for setting it.  For KA, the HipChat token lives in secrets.py.

Here are the instructions for setting the token:

1) In your browser, go to /admin/test_send_to_hipchat
   (This will fail -- you'll get an error of some sort.  But it
   initializes the token in the db.)
2) Now go to admin-console.appspot.com (or /_ah/admin in the dev_appserver).
   Click on 'Datastore Viewer'.  Select the entity kind 'HipchatToken',
   and click 'List entities'.  There should be only one.  Click on it
   (the key name).
3) Under 'token (string)' put in the hipchat token (from secrets.py).
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
    token_record = q.get()
    if token_record:
        hipchat.connection.token = token_record.token
    else:
        # The admin console doesn't let you create a new entity if
        # there are no entities at all of that type.  So create the
        # entity if it doesn't already exist, then the user can edit
        # it via the console.
        db.put(HipchatToken())

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
