import datetime
import hashlib
import os

from google.appengine.ext import db
from google.appengine.api import users


NULL_CATEGORY = '(unknown)'

# Note: I use email address rather than a UserProperty to uniquely
# identify a user.  As per
# http://code.google.com/appengine/docs/python/users/userobjects.html
# a UserProperty is an email+unique id, so if a person changes their
# email the UserProperty also changes; it's not a persistent
# identifier across email changes the way the unique-id alone is.  But
# non-google users can't have a unique id, so if I want to expand the
# snippet server later that won't scale.  So might as well use email
# as our unique identifier.  If someone changes email address and
# wants to take their snippets with them, we can add functionality to
# support that later.


class User(db.Model):
    """User preferences."""
    created = db.DateTimeProperty()
    last_modified = db.DateTimeProperty(auto_now=True)
    email = db.StringProperty(required=True)           # The key to this record
    is_hidden = db.BooleanProperty(default=False)      # hide 'empty' snippets
    category = db.StringProperty(default=NULL_CATEGORY)  # groups snippets
    uses_markdown = db.BooleanProperty(default=True)  # interpret snippet text
    private_snippets = db.BooleanProperty(default=False)  # private by default?
    wants_email = db.BooleanProperty(default=True)     # get nag emails?
    # TODO(csilvers): make a ListProperty instead.
    wants_to_view = db.TextProperty(default='all')     # comma-separated list
    display_name = db.TextProperty(default='')         #  display name of the user


class Snippet(db.Model):
    """Every snippet is identified by the monday of the week it goes with."""
    created = db.DateTimeProperty()
    last_modified = db.DateTimeProperty(auto_now=True)
    display_name = db.StringProperty()        # display name of the user
    email = db.StringProperty(required=True)  # week+email: key to this record
    week = db.DateProperty(required=True)     # the monday of the week
    text = db.TextProperty()
    private = db.BooleanProperty(default=False)       # snippet is private?
    is_markdown = db.BooleanProperty(default=False)   # text is markdown?

    @property
    def email_md5_hash(self):
        m = hashlib.md5()
        m.update(self.email)
        return m.hexdigest()


class AppSettings(db.Model):
    """Application-wide preferences."""
    created = db.DateTimeProperty()
    last_modified = db.DateTimeProperty(auto_now=True)
    # Application settings
    domains = db.StringListProperty(required=True)
    hostname = db.StringProperty(required=True)           # used for emails
    default_private = db.BooleanProperty(default=False)   # new-user default
    default_markdown = db.BooleanProperty(default=True)   # new-user default
    default_email = db.BooleanProperty(default=True)      # new-user default
    # Chat and email settings
    email_from = db.StringProperty(default='')
    slack_channel = db.StringProperty(default='')
    slack_token = db.StringProperty(default='')
    slack_slash_token = db.StringProperty(default='')

    @staticmethod
    def get(create_if_missing=False, domains=None):
        """Return the global app settings, or raise ValueError if none found.

        If create_if_missing is true, we create app settings if none
        are found, rather than raising a ValueError.  The app settings
        are initialized with the given value for 'domains'.  The new
        entity is *not* put to the datastore.
        """
        retval = AppSettings.get_by_key_name('global_settings')
        if retval:
            return retval
        elif create_if_missing:
            # We default to sending email, and having it look like it's
            # comint from the current user.  We add a '+snippets' in there
            # to allow for filtering
            email_address = users.get_current_user().email()
            email_address = email_address.replace('@', '+snippets@')
            email_address = 'Snippet Server <%s>' % email_address
            # We also default to server hostname being the hostname that
            # you accessed the site on here.
            hostname = '%s://%s' % (os.environ.get('wsgi.url_scheme', 'http'),
                                    os.environ['HTTP_HOST'])
            return AppSettings(key_name='global_settings',
                               created=datetime.datetime.now(),
                               domains=domains,
                               hostname=hostname,
                               email_from=email_address)
        else:
            raise ValueError("Need to set global application settings.")
