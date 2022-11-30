"""Snippets server.

The main server code for Weekly Snippets.  Users can add a summary of
what they did in the last week, and browse other people's snippets.
They will also get weekly mail pointing to a webpage with everyone's
snippets in them.
"""

__author__ = 'Craig Silverstein <csilvers@khanacademy.org>'

import datetime
from functools import cmp_to_key
import logging
import os
import re
import time
import urllib

from google.appengine.api import mail, wrap_wsgi_app
from google.appengine.api import users
from google.cloud import ndb
import google.cloud.logging
import flask

import hipchatlib
import models
import slacklib
import util

# Set up cloud logging
logging_client = google.cloud.logging.Client()
logging_client.setup_logging(log_level=logging.INFO)

# This allows mocking in a different day, for testing.
_TODAY_FN = datetime.datetime.now

app = flask.Flask(__name__)
app.wsgi_app = wrap_wsgi_app(app.wsgi_app)


class NDBMiddleware:
    """WSGI middleware to wrap the app in Google Cloud NDB context"""
    def __init__(self, app):
        self.app = app
        self.client = ndb.Client()

    def __call__(self, environ, start_response):
        with self.client.context():
            return self.app(environ, start_response)

app.wsgi_app = NDBMiddleware(app.wsgi_app)


@app.template_filter("readable_date")
def _readable_date_filter(value: datetime.date):
    return value.strftime('%B %d, %Y').replace(' 0', ' ')


@app.template_filter("iso_date")
def _iso_date_filter(value: datetime.date):
    return value.strftime("%m-%d-%Y")


def _login_page(request):
    """Redirect the user to a page where they can log in."""
    return flask.redirect(users.create_login_url(request.url))


def _current_user_email():
    """Return the logged-in user's email address, converted into lowercase."""
    return users.get_current_user().email().lower()


def _get_or_create_user(email, put_new_user=True):
    """Return the user object with the given email, creating it if needed.

    Considers the permissions scope of the currently logged in web user,
    and raises an IndexError if the currently logged in user is not the same as
    the queried email address (or is an admin).

    NOTE: Any access that causes _get_or_create_user() is an access that
    indicates the user is active again, so they are "unhidden" in the db.
    """
    user = util.get_user(email)
    if user:
        if user.is_hidden:
            # Any access that causes _get_or_create_user() is an access
            # that indicates the user is active again, so un-hide them.
            # TODO(csilvers): move this get/update/put atomic into a txn
            user.is_hidden = False
            user.put()
    elif not _logged_in_user_has_permission_for(email):
        # TODO(csilvers): turn this into a 403 somewhere
        raise IndexError('User "%s" not found; did you specify'
                         ' the full email address?' % email)
    else:
        # You can only create a new user under one of the app-listed domains.
        try:
            app_settings = models.AppSettings.get()
        except ValueError:
            # TODO(csilvers): do this instead:
            #                 /admin/settings?redirect_to=user_setting
            # return None
            raise  # TODO(benley) implement Redirect exception

        domain = email.split('@')[-1]
        allowed_domains = app_settings.domains
        if domain not in allowed_domains:
            # TODO(csilvers): turn this into a 403 somewhere
            raise RuntimeError('Permission denied: '
                               'This app is for users from %s.'
                               ' But you are from %s.'
                               % (' or '.join(allowed_domains), domain))

        # Set the user defaults based on the global app defaults.
        user = models.User(created=_TODAY_FN(),
                           email=email,
                           uses_markdown=app_settings.default_markdown,
                           private_snippets=app_settings.default_private,
                           wants_email=app_settings.default_email)
        if put_new_user:
            user.put()
            user.key.get()  # ensure db consistency for HRD
    return user


def _logged_in_user_has_permission_for(email):
    """True if the current logged-in appengine user can edit this user."""
    return (email == _current_user_email()) or users.is_current_user_admin()


def _can_view_private_snippets(my_email, snippet_email):
    """Return true if I have permission to view other's private snippet.

    I have permission to view if I am in the same domain as the person
    who wrote the snippet (domain is everything following the @ in the
    email).

    Arguments:
      my_email: the email address of the currently logged in user
      snippet_email: the email address of the snippet we're trying to view.

    Returns:
      True if my_email has permission to view snippet_email's private
      emails, or False else.
    """
    my_at = my_email.rfind('@')
    snippet_at = snippet_email.rfind('@')
    if my_at == -1 or snippet_at == -1:
        return False    # be safe
    return my_email[my_at:] == snippet_email[snippet_at:]


def _send_to_chat(msg, url_path):
    """Send a message to the main room/channel for active chat integrations."""
    try:
        app_settings = models.AppSettings.get()
    except ValueError:
        logging.warning('Not sending to chat: app settings not configured')
        return

    msg = "%s %s%s" % (msg, app_settings.hostname, url_path)

    hipchat_room = app_settings.hipchat_room
    if hipchat_room:
        hipchatlib.send_to_hipchat_room(hipchat_room, msg)

    slack_channel = app_settings.slack_channel
    if slack_channel:
        slacklib.send_to_slack_channel(slack_channel, msg)


@app.route("/")
def user_page_handler():
    """Show all the snippets for a single user."""

    if not users.get_current_user():
        return _login_page(flask.request)

    user_email = flask.request.args.get('u', _current_user_email())
    user = util.get_user(user_email)

    if not user:
        # If there are no app settings, set those up before setting
        # up the user settings.
        if users.is_current_user_admin():
            try:
                models.AppSettings.get()
            except ValueError:
                return flask.redirect(
                    "/admin/settings?redirect_to=user_setting"
                    "&msg=Welcome+to+the+snippet+server!+"
                    "Please+take+a+moment+to+configure+it.")

        template_values = {
            'new_user': True,
            'login_url': users.create_login_url(flask.request.url),
            'logout_url': users.create_logout_url('/'),
            'username': user_email,
        }
        return flask.render_template('new_user.html', **template_values)

    snippets = util.snippets_for_user(user_email)

    if not _can_view_private_snippets(_current_user_email(), user_email):
        snippets = [snippet for snippet in snippets if not snippet.private]
    snippets = util.fill_in_missing_snippets(snippets, user,
                                             user_email, _TODAY_FN())
    snippets.reverse()                  # get to newest snippet first

    template_values = {
        'logout_url': users.create_logout_url('/'),
        'message': flask.request.args.get('msg'),
        'username': user_email,
        'is_admin': users.is_current_user_admin(),
        'domain': user_email.split('@')[-1],
        'view_week': util.existingsnippet_monday(_TODAY_FN()),
        # Snippets for the week of <one week ago> are due today.
        'one_week_ago': _TODAY_FN().date() - datetime.timedelta(days=7),
        'eight_days_ago': _TODAY_FN().date() - datetime.timedelta(days=8),
        'editable': (_logged_in_user_has_permission_for(user_email) and
                     flask.request.args.get('edit', '1') == '1'),
        'user': user,
        'snippets': snippets,
        'null_category': models.NULL_CATEGORY,
    }
    return flask.render_template('user_snippets.html', **template_values)


def _title_case(s):
    """Like string.title(), but does not uppercase 'and'."""
    # Smarter would be to use 'pip install titlecase'.
    SMALL = 'a|an|and|as|at|but|by|en|for|if|in|of|on|or|the|to|v\.?|via|vs\.?'
    # We purposefully don't match small words at the beginning of a string.
    SMALL_RE = re.compile(r' (%s)\b' % SMALL, re.I)
    return SMALL_RE.sub(lambda m: ' ' + m.group(1).lower(), s.title().strip())


@app.route("/weekly")
def summary_page_handler():
    """Show all the snippets for a single week."""

    if not users.get_current_user():
        return _login_page(flask.request)

    week_string = flask.request.args.get('week')
    if week_string:
        week = datetime.datetime.strptime(week_string, '%m-%d-%Y').date()
    else:
        week = util.existingsnippet_monday(_TODAY_FN())

    snippets_q = models.Snippet.query(
        models.Snippet.week == week
    )
    snippets = snippets_q.fetch(1000)   # good for many users...
    # TODO(csilvers): filter based on wants_to_view

    # Get all the user records so we can categorize snippets.
    user_q = models.User.query()
    results = user_q.fetch(1000)
    email_to_category = {}
    email_to_user = {}
    for result in results:
        # People aren't very good about capitalizing their
        # categories consistently, so we enforce title-case,
        # with exceptions for 'and'.
        email_to_category[result.email] = _title_case(result.category)
        email_to_user[result.email] = result

    # Collect the snippets and users by category.  As we see each email,
    # delete it from email_to_category.  At the end of this,
    # email_to_category will hold people who did not give
    # snippets this week.
    snippets_and_users_by_category = {}
    for snippet in snippets:
        # Ignore this snippet if we don't have permission to view it.
        if (snippet.private and
                not _can_view_private_snippets(_current_user_email(),
                                                snippet.email)):
            continue
        category = email_to_category.get(
            snippet.email, models.NULL_CATEGORY
        )
        if snippet.email in email_to_user:
            snippets_and_users_by_category.setdefault(category, []).append(
                (snippet, email_to_user[snippet.email])
            )
        else:
            snippets_and_users_by_category.setdefault(category, []).append(
                (snippet, models.User(email=snippet.email))
            )

        if snippet.email in email_to_category:
            del email_to_category[snippet.email]

    # Add in empty snippets for the people who didn't have any --
    # unless a user is marked 'hidden'.  (That's what 'hidden'
    # means: pretend they don't exist until they have a non-empty
    # snippet again.)
    for (email, category) in email_to_category.items():
        if not email_to_user[email].is_hidden:
            snippet = models.Snippet(email=email, week=week)
            snippets_and_users_by_category.setdefault(category, []).append(
                (snippet, email_to_user[snippet.email])
            )

    # Now get a sorted list, categories in alphabetical order and
    # each snippet-author within the category in alphabetical
    # order.
    # The data structure is ((category, ((snippet, user), ...)), ...)
    categories_and_snippets = []
    for category, snippets_and_users in snippets_and_users_by_category.items():
        # This looks stupid but python no longer allows lambda (snippet, user): snippet.email
        snippets_and_users.sort(key=lambda snippet_user: snippet_user[0].email)
        categories_and_snippets.append((category, snippets_and_users))
    categories_and_snippets.sort()

    template_values = {
        'logout_url': users.create_logout_url('/'),
        'message': flask.request.args.get('msg'),
        # Used only to switch to 'username' mode and to modify settings.
        'username': _current_user_email(),
        'is_admin': users.is_current_user_admin(),
        'prev_week': week - datetime.timedelta(7),
        'view_week': week,
        'next_week': week + datetime.timedelta(7),
        'categories_and_snippets': categories_and_snippets,
    }
    return flask.render_template('weekly_snippets.html', **template_values)


def update_snippet(email: str,
                   week: datetime.date,
                   text: str,
                   private: bool,
                   is_markdown: bool):
    assert week.weekday() == 0, 'passed-in date must be a Monday'

    # TODO(csilvers): make this get-update-put atomic.
    # (maybe make the snippet id be email + week).
    q = models.Snippet.query(
               models.Snippet.email == email,
               models.Snippet.week == week
    )
    snippet = q.get()

    # When adding a snippet, make sure we create a user record for
    # that email as well, if it doesn't already exist.
    user = _get_or_create_user(email)

    # Store user's display_name in snippet so that if a user is later
    # deleted, we could still show his / her display_name.
    if snippet:
        snippet.text = text   # just update the snippet text
        snippet.display_name = user.display_name
        snippet.private = private
        snippet.is_markdown = is_markdown
    else:
        # add the snippet to the db
        snippet = models.Snippet(created=_TODAY_FN(),
                                 display_name=user.display_name,
                                 email=email, week=week,
                                 text=text, private=private,
                                 is_markdown=is_markdown)
    snippet.put()
    snippet.key.get()  # ensure db consistency for HRD


@app.route("/update_snippet", methods=["POST", "GET"])
def update_snippet_handler():

    if flask.request.method == "POST":
        data = flask.request.form
    elif flask.request.method == "GET":
        data = flask.request.args

    email = data.get('u', _current_user_email())
    week_string = data.get('week')
    week = datetime.datetime.strptime(week_string, '%m-%d-%Y').date()
    text = data.get('snippet')
    private = data.get('private') == 'True'
    is_markdown = data.get('is_markdown') == 'True'

    if flask.request.method == "POST":
        """handle ajax updates via POST

        in particular, return status via json rather than redirects and
        hard exceptions. This isn't actually RESTy, it's just status
        codes and json.
        """
        # TODO(marcos): consider using PUT?

        if not users.get_current_user():
            # 403s are the catch-all 'please log in error' here
            return flask.make_response({"status": 403, "message": "not logged in"}, 403)

        if not _logged_in_user_has_permission_for(email):
            # TODO(marcos): present these messages to the ajax client
            error = ('You do not have permissions to update user'
                     ' snippets for %s' % email)
            return flask.make_response({"status": 403, "message": error}, 403)

        update_snippet(email, week, text, private, is_markdown)
        return flask.make_response({"status": 200, "message": "ok"})

    elif flask.request.method == "GET":
        if not users.get_current_user():
            return _login_page(flask.request)

        if not _logged_in_user_has_permission_for(email):
            # TODO(benley): Add a friendlier error page template, maybe?
            return flask.make_response("You do not have permission to update"
                                       " user snippets for %s" % email, 403)

        update_snippet(email, week, text, private, is_markdown)
        return flask.redirect("/?msg=Snippet+saved&u=%s" % urllib.parse.quote(email))


@app.route("/settings")
def settings_handler():
    """Page to display a user's settings (from class User) for modification."""

    if not users.get_current_user():
        return _login_page(flask.request)

    user_email = flask.request.args.get('u', _current_user_email())
    if not _logged_in_user_has_permission_for(user_email):
        return flask.make_response('You do not have permissions to view user'
                                   ' settings for %s' % user_email, 403)
    # We won't put() the new user until the settings are saved.
    user = _get_or_create_user(user_email, put_new_user=False)

    # NOTE: this will break if you explicitly set the key when creating the
    #       user entity!
    #       See https://groups.google.com/g/google-appengine/c/Tm8NDWIvc70
    if user.key and user.key.id():
        is_new_user = False
    else:
        is_new_user = True

    template_values = {
        'logout_url': users.create_logout_url('/'),
        'message': flask.request.args.get('msg'),
        'username': user.email,
        'is_admin': users.is_current_user_admin(),
        'view_week': util.existingsnippet_monday(_TODAY_FN()),
        'user': user,
        'is_new_user': is_new_user,
        'redirect_to': flask.request.args.get('redirect_to', ''),
        # We could get this from user, but we want to replace
        # commas with newlines for printing.
        'wants_to_view': user.wants_to_view.replace(',', '\n'),
    }
    return flask.render_template('settings.html', **template_values)


@app.route("/update_settings")
def update_settings_handler():
    """Updates the db with modifications from the Settings page."""

    if not users.get_current_user():
        return _login_page(flask.request)

    user_email = flask.request.args.get('u', _current_user_email())
    if not _logged_in_user_has_permission_for(user_email):
        return flask.make_response('You do not have permissions to modify user'
                                   ' settings for %s' % user_email, 403)
    # TODO(csilvers): make this get/update/put atomic (put in a txn)
    user = _get_or_create_user(user_email)

    # First, check if the user clicked on 'delete' or 'hide'
    # rather than 'save'.
    if flask.request.args.get('hide'):
        user.is_hidden = True
        user.put()
        time.sleep(0.1)   # some time for eventual consistency
        return flask.redirect('/weekly?msg=You+are+now+hidden.+Have+a+nice+day!')
    elif flask.request.args.get('delete'):
        user.delete()
        return flask.redirect('/weekly?msg=Your+account+has+been+deleted.+'
                              '(Note+your+existing+snippets+have+NOT+been+'
                              'deleted.)+Have+a+nice+day!')

    display_name = flask.request.args.get('display_name')
    category = flask.request.args.get('category')
    uses_markdown = flask.request.args.get('markdown') == 'yes'
    private_snippets = flask.request.args.get('private') == 'yes'
    wants_email = flask.request.args.get('reminder_email') == 'yes'

    # We want this list to be comma-separated, but people are
    # likely to use whitespace to separate as well.  Convert here.
    wants_to_view = flask.request.args.get('to_view')
    wants_to_view = re.sub(r'\s+', ',', wants_to_view)
    wants_to_view = wants_to_view.split(',')
    wants_to_view = [w for w in wants_to_view if w]   # deal with ',,'
    wants_to_view = ','.join(wants_to_view)  # TODO(csilvers): keep as list

    # Changing their settings is the kind of activity that unhides
    # someone who was hidden, unless they specifically ask to be
    # hidden.
    is_hidden = flask.request.args.get('is_hidden', 'no') == 'yes'

    user.is_hidden = is_hidden
    user.display_name = display_name
    user.category = category or models.NULL_CATEGORY
    user.uses_markdown = uses_markdown
    user.private_snippets = private_snippets
    user.wants_email = wants_email
    user.wants_to_view = wants_to_view
    user.put()
    user.key.get()  # ensure db consistency for HRD

    redirect_to = flask.request.args.get('redirect_to')
    if redirect_to == 'snippet_entry':   # true for new_user.html
        return flask.redirect('/?u=%s' % urllib.parse.quote(user_email))
    else:
        return flask.redirect("/settings?msg=Changes+saved&u=%s"
                              % urllib.parse.quote(user_email))


@app.route("/admin/settings")
def admin_settings_handler():
    """Page to display settings for the whole app, for modification.

    This page should be restricted to admin users via app.yaml.
    """
    my_domain = _current_user_email().split('@')[-1]
    app_settings = models.AppSettings.get(create_if_missing=True,
                                            domains=[my_domain])

    template_values = {
        'logout_url': users.create_logout_url('/'),
        'message': flask.request.args.get('msg'),
        'username': _current_user_email(),
        'is_admin': users.is_current_user_admin(),
        'view_week': util.existingsnippet_monday(_TODAY_FN()),
        'redirect_to': flask.request.args.get('redirect_to', ''),
        'settings': app_settings,
        'slack_slash_commands': slacklib.command_usage().strip()
    }
    return flask.render_template('app_settings.html', **template_values)


@app.route("/admin/update_settings", methods=["POST"])
def admin_update_settings_handler():
    """Updates the db with modifications from the App-Settings page.

    This page should be restricted to admin users via app.yaml.
    """
    _get_or_create_user(_current_user_email())

    domains = flask.request.form.get('domains')
    default_private = flask.request.form.get('private') == 'yes'
    default_markdown = flask.request.form.get('markdown') == 'yes'
    default_email = flask.request.form.get('reminder_email') == 'yes'
    email_from = flask.request.form.get('email_from')
    hipchat_room = flask.request.form.get('hipchat_room')
    hipchat_token = flask.request.form.get('hipchat_token')
    hostname = flask.request.form.get('hostname')
    slack_channel = flask.request.form.get('slack_channel')
    slack_token = flask.request.form.get('slack_token')
    slack_slash_token = flask.request.form.get('slack_slash_token')

    # Turn domains into a list.  Allow whitespace or comma to separate.
    domains = re.sub(r'\s+', ',', domains)
    domains = [d for d in domains.split(',') if d]

    @ndb.transactional()
    def update_settings():
        app_settings = models.AppSettings.get(create_if_missing=True,
                                              domains=domains)
        app_settings.domains = domains
        app_settings.default_private = default_private
        app_settings.default_markdown = default_markdown
        app_settings.default_email = default_email
        app_settings.email_from = email_from
        app_settings.hipchat_room = hipchat_room
        app_settings.hipchat_token = hipchat_token
        app_settings.hostname = hostname
        app_settings.slack_channel = slack_channel
        app_settings.slack_token = slack_token
        app_settings.slack_slash_token = slack_slash_token
        app_settings.put()

    update_settings()

    redirect_to = flask.request.form.get('redirect_to')
    if redirect_to == 'user_setting':   # true for new_user.html
        return flask.redirect('/settings?redirect_to=snippet_entry'
                              '&msg=Now+enter+your+personal+user+settings.')
    else:
        return flask.redirect("/admin/settings?msg=Changes+saved")


def cmp(a, b):
    """Python 2's cmp function, used in /admin/manage_users handler"""
    return (a > b) - (a < b)


@app.route("/admin/manage_users")
def admin_manage_users_handler():
    """Lets admins delete and otherwise manage users."""
    # options are 'email', 'creation_time', 'last_snippet_time'
    sort_by = flask.request.args.get('sort_by', 'creation_time')

    # First, check if the user had clicked on a button.
    for name, value in flask.request.form.items():
        if name.startswith('hide '):
            email_of_user_to_hide = name[len('hide '):]
            # TODO(csilvers): move this get/update/put atomic into a txn
            user = util.get_user_or_die(email_of_user_to_hide)
            user.is_hidden = True
            user.put()
            time.sleep(0.1)   # encourage eventual consistency
            return flask.redirect('/admin/manage_users?sort_by=%s&msg=%s+hidden'
                                  % (sort_by, email_of_user_to_hide))
        if name.startswith('unhide '):
            email_of_user_to_unhide = name[len('unhide '):]
            # TODO(csilvers): move this get/update/put atomic into a txn
            user = util.get_user_or_die(email_of_user_to_unhide)
            user.is_hidden = False
            user.put()
            time.sleep(0.1)   # encourage eventual consistency
            return flask.redirect('/admin/manage_users?sort_by=%s&msg=%s+unhidden'
                                  % (sort_by, email_of_user_to_unhide))
        if name.startswith('delete '):
            email_of_user_to_delete = name[len('delete '):]
            user = util.get_user_or_die(email_of_user_to_delete)
            user.delete()
            time.sleep(0.1)   # encourage eventual consistency
            return flask.redirect('/admin/manage_users?sort_by=%s&msg=%s+deleted'
                                  % (sort_by, email_of_user_to_delete))

    user_q = models.User.query()
    results = user_q.fetch(1000)

    # Tuple: (email, is-hidden, creation-time, days since last snippet)
    user_data = []
    for user in results:
        # Get the last snippet for that user.
        last_snippet = util.most_recent_snippet_for_user(user.email)
        if last_snippet:
            seconds_since_snippet = (
                (_TODAY_FN().date() - last_snippet.week).total_seconds())
            weeks_since_snippet = int(
                seconds_since_snippet /
                datetime.timedelta(days=7).total_seconds())
        else:
            weeks_since_snippet = None
        user_data.append((user.email, user.is_hidden,
                          user.created, weeks_since_snippet))

    # We have to use 'cmp' here since we want ascending in the
    # primary key and descending in the secondary key, sometimes.
    if sort_by == 'email':
        user_data.sort(key=cmp_to_key(lambda x, y: cmp(x[0], y[0])))
    elif sort_by == 'creation_time':
        user_data.sort(key=cmp_to_key(
            lambda x, y: (-cmp(x[2] or datetime.datetime.min,
                               y[2] or datetime.datetime.min)
                          or cmp(x[0], y[0]))))
    elif sort_by == 'last_snippet_time':
        user_data.sort(key=cmp_to_key(
            lambda x, y: (-cmp(1000 if x[3] is None else x[3],
                               1000 if y[3] is None else y[3])
                          or cmp(x[0], y[0]))))
    else:
        raise ValueError('Invalid sort_by value "%s"' % sort_by)

    template_values = {
        'logout_url': users.create_logout_url('/'),
        'message': flask.request.args.get('msg'),
        'username': _current_user_email(),
        'is_admin': users.is_current_user_admin(),
        'view_week': util.existingsnippet_monday(_TODAY_FN()),
        'user_data': user_data,
        'sort_by': sort_by,
    }
    return flask.render_template('manage_users.html', **template_values)


# The following two classes are called by cron.


def _get_email_to_current_snippet_map(today: datetime.datetime) -> dict[str, bool]:
    """Return a map from email to True if they've written snippets this week.

    Goes through all users registered on the system, and checks if
    they have a snippet in the db for the appropriate snippet-week for
    'today'.  If so, they get entered into the return-map with value
    True.  If not, they have value False.

    Note that users whose 'wants_email' field is set to False will not
    be included in either list.

    Arguments:
      today: a datetime.datetime object representing the
        'current' day.  We use the normal algorithm to determine what is
        the most recent snippet-week for this day.

    Returns:
      a map from email (user.email for each user) to True or False,
      depending on if they've written snippets for this week or not.
    """
    user_q = models.User.query()
    users = user_q.fetch(1000)
    retval = {}
    for user in users:
        if not user.wants_email:         # ignore this user
            continue
        retval[user.email] = False       # assume the worst, for now

    week = util.existingsnippet_monday(today)
    snippets_q = models.Snippet.query(
        models.Snippet.week == week
    )
    snippets = snippets_q.fetch(1000)
    for snippet in snippets:
        if snippet.email in retval:      # don't introduce new keys here
            retval[snippet.email] = True

    return retval


def _maybe_send_snippets_mail(to, subject, template_path, template_values):
    try:
        app_settings = models.AppSettings.get()
    except ValueError:
        logging.error('Not sending email: app settings are not configured.')
        return
    if not app_settings.email_from:
        return

    template_values.setdefault('hostname', app_settings.hostname)

    mail.send_mail(sender=app_settings.email_from,
                   to=to,
                   subject=subject,
                   body=flask.render_template(template_path,
                                              **template_values))
    # Appengine has a quota of 32 emails per minute:
    #    https://developers.google.com/appengine/docs/quotas#Mail
    # We pause 2 seconds between each email to make sure we
    # don't go over that.
    time.sleep(2)


@app.route("/admin/send_friday_reminder_chat")
def admin_send_friday_reminder_chat_handler() -> flask.Response:
    """Send a chat message to the configured chat room(s)."""
    msg = 'Reminder: Weekly snippets due Monday at 5pm.'
    _send_to_chat(msg, "/")
    return flask.make_response({"status": 200, "message": "Sent friday reminder chat"})


@app.route("/admin/send_reminder_email")
def admin_send_reminder_email_handler() -> flask.Response:
    """Send an email to everyone who doesn't have a snippet for this week."""

    def _send_mail(email):
        template_values = {}
        _maybe_send_snippets_mail(email, 'Weekly snippets due today at 5pm',
                                  'reminder_email.txt', template_values)

    email_to_has_snippet = _get_email_to_current_snippet_map(_TODAY_FN())
    for user_email, has_snippet in email_to_has_snippet.items():
        if not has_snippet:
            _send_mail(user_email)
            logging.debug('sent reminder email to %s', user_email)
        else:
            logging.debug('did not send reminder email to %s: '
                          'has a snippet already', user_email)

    msg = 'Reminder: Weekly snippets due today at 5pm.'
    _send_to_chat(msg, "/")
    return flask.make_response({"status": 200, "message": "Sent reminder emails"})


@app.route("/admin/send_view_email")
def admin_send_view_email_handler() -> flask.Response:
    """Send an email to everyone to look at the week's snippets."""

    def _send_mail(email, has_snippets):
        template_values = {'has_snippets': has_snippets}
        _maybe_send_snippets_mail(email, 'Weekly snippets are ready!',
                                  'view_email.txt', template_values)

    email_to_has_snippet = _get_email_to_current_snippet_map(_TODAY_FN())
    for user_email, has_snippet in email_to_has_snippet.items():
        _send_mail(user_email, has_snippet)
        logging.debug('sent "view" email to %s', user_email)

    msg = 'Weekly snippets are ready!'
    _send_to_chat(msg, "/weekly")
    return flask.make_response({"status": 200, "message": "Sent 'snippets are ready' emails"})


app.add_url_rule("/slack", view_func=slacklib.slash_command_handler,
                 methods=["POST"])
app.add_url_rule("/admin/test_send_to_hipchat",
                 view_func=hipchatlib.test_send_to_hipchat_handler)

if __name__ == '__main__':
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. You
    # can configure startup instructions by adding `entrypoint` to app.yaml.
    app.run(host='127.0.0.1', debug=True)
