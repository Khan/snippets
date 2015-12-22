from google.appengine.ext import db
import hashlib

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


class Snippet(db.Model):
    """Every snippet is identified by the monday of the week it goes with."""
    created = db.DateTimeProperty()
    last_modified = db.DateTimeProperty(auto_now=True)
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
