"""Snippets server.

The main server code for Weekly Snippets.  Users can add a summary of
what they did in the last week, and browse other people's snippets.
They will also get weekly mail pointing to a webpage with everyone's
snippets in them.
"""

__author__ = 'Craig Silverstein <csilvers@khanacademy.org>'

import datetime
import logging
import os
import re
import time
import urllib

from google.appengine.api import mail
from google.appengine.api import users
from google.appengine.ext import db
import webapp2
from webapp2_extras import jinja2

import models
import slacklib
import util


# This allows mocking in a different day, for testing.
_TODAY_FN = datetime.datetime.now


jinja2.default_config['template_path'] = os.path.join(
    os.path.dirname(__file__),
    "templates"
)
jinja2.default_config['filters'] = {
    'readable_date': (
        lambda value: value.strftime('%B %d, %Y').replace(' 0', ' ')),
    'iso_date': (
        lambda value: value.strftime('%m-%d-%Y')),
}


def _login_page(request, redirector):
    """Redirect the user to a page where they can log in."""
    redirector.redirect(users.create_login_url(request.uri))


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
            return None

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
            db.put(user)
            db.get(user.key())    # ensure db consistency for HRD
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

    slack_channel = app_settings.slack_channel
    if slack_channel:
        slacklib.send_to_slack_channel(slack_channel, msg)


class BaseHandler(webapp2.RequestHandler):
    """Set up as per the jinja2.py docstring."""
    @webapp2.cached_property
    def jinja2(self):
        return jinja2.get_jinja2()

    def render_response(self, template_filename, context):
        html = self.jinja2.render_template(template_filename, **context)
        self.response.write(html)


class UserPage(BaseHandler):
    """Show all the snippets for a single user."""

    def get(self):
        if not users.get_current_user():
            return _login_page(self.request, self)

        user_email = self.request.get('u', _current_user_email())
        user = util.get_user(user_email)

        if not user:
            # If there are no app settings, set those up before setting
            # up the user settings.
            if users.is_current_user_admin():
                try:
                    models.AppSettings.get()
                except ValueError:
                    self.redirect("/admin/settings?redirect_to=user_setting"
                                  "&msg=Welcome+to+the+snippet+server!+"
                                  "Please+take+a+moment+to+configure+it.")
                    return

            template_values = {
                'new_user': True,
                'login_url': users.create_login_url(self.request.uri),
                'logout_url': users.create_logout_url('/'),
                'username': user_email,
            }
            self.render_response('new_user.html', template_values)
            return

        snippets = util.snippets_for_user(user_email)

        if not _can_view_private_snippets(_current_user_email(), user_email):
            snippets = [snippet for snippet in snippets if not snippet.private]
        snippets = util.fill_in_missing_snippets(snippets, user,
                                                 user_email, _TODAY_FN())
        snippets.reverse()                  # get to newest snippet first

        template_values = {
            'logout_url': users.create_logout_url('/'),
            'message': self.request.get('msg'),
            'username': user_email,
            'is_admin': users.is_current_user_admin(),
            'domain': user_email.split('@')[-1],
            'view_week': util.existingsnippet_monday(_TODAY_FN()),
            # Snippets for the week of <one week ago> are due today.
            'one_week_ago': _TODAY_FN().date() - datetime.timedelta(days=7),
            'eight_days_ago': _TODAY_FN().date() - datetime.timedelta(days=8),
            'editable': (_logged_in_user_has_permission_for(user_email) and
                         self.request.get('edit', '1') == '1'),
            'user': user,
            'snippets': snippets,
            'null_category': models.NULL_CATEGORY,
        }
        self.render_response('user_snippets.html', template_values)


def _title_case(s):
    """Like string.title(), but does not uppercase 'and'."""
    # Smarter would be to use 'pip install titlecase'.
    SMALL = 'a|an|and|as|at|but|by|en|for|if|in|of|on|or|the|to|v\.?|via|vs\.?'
    # We purposefully don't match small words at the beginning of a string.
    SMALL_RE = re.compile(r' (%s)\b' % SMALL, re.I)
    return SMALL_RE.sub(lambda m: ' ' + m.group(1).lower(), s.title().strip())


class SummaryPage(BaseHandler):
    """Show all the snippets for a single week."""

    def get(self):
        if not users.get_current_user():
            return _login_page(self.request, self)

        week_string = self.request.get('week')
        if week_string:
            week = datetime.datetime.strptime(week_string, '%m-%d-%Y').date()
        else:
            week = util.existingsnippet_monday(_TODAY_FN())

        snippets_q = models.Snippet.all()
        snippets_q.filter('week = ', week)
        snippets = snippets_q.fetch(1000)   # good for many users...
        # TODO(csilvers): filter based on wants_to_view

        # Get all the user records so we can categorize snippets.
        user_q = models.User.all()
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
        for (email, category) in email_to_category.iteritems():
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
        for (category,
             snippets_and_users) in snippets_and_users_by_category.iteritems():
            snippets_and_users.sort(key=lambda (snippet, user): snippet.email)
            categories_and_snippets.append((category, snippets_and_users))
        categories_and_snippets.sort()

        template_values = {
            'logout_url': users.create_logout_url('/'),
            'message': self.request.get('msg'),
            # Used only to switch to 'username' mode and to modify settings.
            'username': _current_user_email(),
            'is_admin': users.is_current_user_admin(),
            'prev_week': week - datetime.timedelta(7),
            'view_week': week,
            'next_week': week + datetime.timedelta(7),
            'categories_and_snippets': categories_and_snippets,
        }
        self.render_response('weekly_snippets.html', template_values)


class UpdateSnippet(BaseHandler):
    def update_snippet(self, email):
        week_string = self.request.get('week')
        week = datetime.datetime.strptime(week_string, '%m-%d-%Y').date()
        assert week.weekday() == 0, 'passed-in date must be a Monday'

        text = self.request.get('snippet')

        private = self.request.get('private') == 'True'
        is_markdown = self.request.get('is_markdown') == 'True'

        # TODO(csilvers): make this get-update-put atomic.
        # (maybe make the snippet id be email + week).
        q = models.Snippet.all()
        q.filter('email = ', email)
        q.filter('week = ', week)
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
        db.put(snippet)
        db.get(snippet.key())  # ensure db consistency for HRD

        self.response.set_status(200)

    def post(self):
        """handle ajax updates via POST

        in particular, return status via json rather than redirects and
        hard exceptions. This isn't actually RESTy, it's just status
        codes and json.
        """
        # TODO(marcos): consider using PUT?

        self.response.headers['Content-Type'] = 'application/json'

        if not users.get_current_user():
            # 403s are the catch-all 'please log in error' here
            self.response.set_status(403)
            self.response.out.write('{"status": 403, '
                                    '"message": "not logged in"}')
            return

        email = self.request.get('u', _current_user_email())

        if not _logged_in_user_has_permission_for(email):
            # TODO(marcos): present these messages to the ajax client
            self.response.set_status(403)
            error = ('You do not have permissions to update user'
                     ' snippets for %s' % email)
            self.response.out.write('{"status": 403, '
                                    '"message": "%s"}' % error)
            return

        self.update_snippet(email)
        self.response.out.write('{"status": 200, "message": "ok"}')

    def get(self):
        if not users.get_current_user():
            return _login_page(self.request, self)

        email = self.request.get('u', _current_user_email())
        if not _logged_in_user_has_permission_for(email):
            # TODO(csilvers): return a 403 here instead.
            raise RuntimeError('You do not have permissions to update user'
                               ' snippets for %s' % email)

        self.update_snippet(email)

        email = self.request.get('u', _current_user_email())
        self.redirect("/?msg=Snippet+saved&u=%s" % urllib.quote(email))


class Settings(BaseHandler):
    """Page to display a user's settings (from class User) for modification."""

    def get(self):
        if not users.get_current_user():
            return _login_page(self.request, self)

        user_email = self.request.get('u', _current_user_email())
        if not _logged_in_user_has_permission_for(user_email):
            # TODO(csilvers): return a 403 here instead.
            raise RuntimeError('You do not have permissions to view user'
                               ' settings for %s' % user_email)
        # We won't put() the new user until the settings are saved.
        user = _get_or_create_user(user_email, put_new_user=False)
        try:
            user.key()
            is_new_user = False
        except db.NotSavedError:
            is_new_user = True

        template_values = {
            'logout_url': users.create_logout_url('/'),
            'message': self.request.get('msg'),
            'username': user.email,
            'is_admin': users.is_current_user_admin(),
            'view_week': util.existingsnippet_monday(_TODAY_FN()),
            'user': user,
            'is_new_user': is_new_user,
            'redirect_to': self.request.get('redirect_to', ''),
            # We could get this from user, but we want to replace
            # commas with newlines for printing.
            'wants_to_view': user.wants_to_view.replace(',', '\n'),
        }
        self.render_response('settings.html', template_values)


class UpdateSettings(BaseHandler):
    """Updates the db with modifications from the Settings page."""

    def get(self):
        if not users.get_current_user():
            return _login_page(self.request, self)

        user_email = self.request.get('u', _current_user_email())
        if not _logged_in_user_has_permission_for(user_email):
            # TODO(csilvers): return a 403 here instead.
            raise RuntimeError('You do not have permissions to modify user'
                               ' settings for %s' % user_email)
        # TODO(csilvers): make this get/update/put atomic (put in a txn)
        user = _get_or_create_user(user_email)

        # First, check if the user clicked on 'delete' or 'hide'
        # rather than 'save'.
        if self.request.get('hide'):
            user.is_hidden = True
            user.put()
            time.sleep(0.1)   # some time for eventual consistency
            self.redirect('/weekly?msg=You+are+now+hidden.+Have+a+nice+day!')
            return
        elif self.request.get('delete'):
            db.delete(user)
            self.redirect('/weekly?msg=Your+account+has+been+deleted.+'
                          '(Note+your+existing+snippets+have+NOT+been+'
                          'deleted.)+Have+a+nice+day!')
            return

        display_name = self.request.get('display_name')
        category = self.request.get('category')
        uses_markdown = self.request.get('markdown') == 'yes'
        private_snippets = self.request.get('private') == 'yes'
        wants_email = self.request.get('reminder_email') == 'yes'

        # We want this list to be comma-separated, but people are
        # likely to use whitespace to separate as well.  Convert here.
        wants_to_view = self.request.get('to_view')
        wants_to_view = re.sub(r'\s+', ',', wants_to_view)
        wants_to_view = wants_to_view.split(',')
        wants_to_view = [w for w in wants_to_view if w]   # deal with ',,'
        wants_to_view = ','.join(wants_to_view)  # TODO(csilvers): keep as list

        # Changing their settings is the kind of activity that unhides
        # someone who was hidden, unless they specifically ask to be
        # hidden.
        is_hidden = self.request.get('is_hidden', 'no') == 'yes'

        user.is_hidden = is_hidden
        user.display_name = display_name
        user.category = category or models.NULL_CATEGORY
        user.uses_markdown = uses_markdown
        user.private_snippets = private_snippets
        user.wants_email = wants_email
        user.wants_to_view = wants_to_view
        db.put(user)
        db.get(user.key())  # ensure db consistency for HRD

        redirect_to = self.request.get('redirect_to')
        if redirect_to == 'snippet_entry':   # true for new_user.html
            self.redirect('/?u=%s' % urllib.quote(user_email))
        else:
            self.redirect("/settings?msg=Changes+saved&u=%s"
                          % urllib.quote(user_email))


class AppSettings(BaseHandler):
    """Page to display settings for the whole app, for modification.

    This page should be restricted to admin users via app.yaml.
    """

    def get(self):
        my_domain = _current_user_email().split('@')[-1]
        app_settings = models.AppSettings.get(create_if_missing=True,
                                              domains=[my_domain])

        template_values = {
            'logout_url': users.create_logout_url('/'),
            'message': self.request.get('msg'),
            'username': _current_user_email(),
            'is_admin': users.is_current_user_admin(),
            'view_week': util.existingsnippet_monday(_TODAY_FN()),
            'redirect_to': self.request.get('redirect_to', ''),
            'settings': app_settings,
            'slack_slash_commands': (
                slacklib.command_usage().strip())
        }
        self.render_response('app_settings.html', template_values)


class UpdateAppSettings(BaseHandler):
    """Updates the db with modifications from the App-Settings page.

    This page should be restricted to admin users via app.yaml.
    """

    def get(self):
        _get_or_create_user(_current_user_email())

        domains = self.request.get('domains')
        default_private = self.request.get('private') == 'yes'
        default_markdown = self.request.get('markdown') == 'yes'
        default_email = self.request.get('reminder_email') == 'yes'
        email_from = self.request.get('email_from')
        slack_channel = self.request.get('slack_channel')
        slack_token = self.request.get('slack_token')
        slack_slash_token = self.request.get('slack_slash_token')

        # Turn domains into a list.  Allow whitespace or comma to separate.
        domains = re.sub(r'\s+', ',', domains)
        domains = [d for d in domains.split(',') if d]

        @db.transactional
        def update_settings():
            app_settings = models.AppSettings.get(create_if_missing=True,
                                                  domains=domains)
            app_settings.domains = domains
            app_settings.default_private = default_private
            app_settings.default_markdown = default_markdown
            app_settings.default_email = default_email
            app_settings.email_from = email_from
            app_settings.slack_channel = slack_channel
            app_settings.slack_token = slack_token
            app_settings.slack_slash_token = slack_slash_token
            app_settings.put()

        update_settings()

        redirect_to = self.request.get('redirect_to')
        if redirect_to == 'user_setting':   # true for new_user.html
            self.redirect('/settings?redirect_to=snippet_entry'
                          '&msg=Now+enter+your+personal+user+settings.')
        else:
            self.redirect("/admin/settings?msg=Changes+saved")


class ManageUsers(BaseHandler):
    """Lets admins delete and otherwise manage users."""

    def get(self):
        # options are 'email', 'creation_time', 'last_snippet_time'
        sort_by = self.request.get('sort_by', 'creation_time')

        # First, check if the user had clicked on a button.
        for (name, value) in self.request.params.iteritems():
            if name.startswith('hide '):
                email_of_user_to_hide = name[len('hide '):]
                # TODO(csilvers): move this get/update/put atomic into a txn
                user = util.get_user_or_die(email_of_user_to_hide)
                user.is_hidden = True
                user.put()
                time.sleep(0.1)   # encourage eventual consistency
                self.redirect('/admin/manage_users?sort_by=%s&msg=%s+hidden'
                              % (sort_by, email_of_user_to_hide))
                return
            if name.startswith('unhide '):
                email_of_user_to_unhide = name[len('unhide '):]
                # TODO(csilvers): move this get/update/put atomic into a txn
                user = util.get_user_or_die(email_of_user_to_unhide)
                user.is_hidden = False
                user.put()
                time.sleep(0.1)   # encourage eventual consistency
                self.redirect('/admin/manage_users?sort_by=%s&msg=%s+unhidden'
                              % (sort_by, email_of_user_to_unhide))
                return
            if name.startswith('delete '):
                email_of_user_to_delete = name[len('delete '):]
                user = util.get_user_or_die(email_of_user_to_delete)
                db.delete(user)
                time.sleep(0.1)   # encourage eventual consistency
                self.redirect('/admin/manage_users?sort_by=%s&msg=%s+deleted'
                              % (sort_by, email_of_user_to_delete))
                return

        user_q = models.User.all()
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
            user_data.sort(lambda x, y: cmp(x[0], y[0]))
        elif sort_by == 'creation_time':
            user_data.sort(lambda x, y: (-cmp(x[2] or datetime.datetime.min,
                                              y[2] or datetime.datetime.min)
                                         or cmp(x[0], y[0])))
        elif sort_by == 'last_snippet_time':
            user_data.sort(lambda x, y: (-cmp(1000 if x[3] is None else x[3],
                                              1000 if y[3] is None else y[3])
                                         or cmp(x[0], y[0])))
        else:
            raise ValueError('Invalid sort_by value "%s"' % sort_by)

        template_values = {
            'logout_url': users.create_logout_url('/'),
            'message': self.request.get('msg'),
            'username': _current_user_email(),
            'is_admin': users.is_current_user_admin(),
            'view_week': util.existingsnippet_monday(_TODAY_FN()),
            'user_data': user_data,
            'sort_by': sort_by,
        }
        self.render_response('manage_users.html', template_values)


# The following two classes are called by cron.


def _get_email_to_current_snippet_map(today):
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
    user_q = models.User.all()
    users = user_q.fetch(1000)
    retval = {}
    for user in users:
        if not user.wants_email:         # ignore this user
            continue
        retval[user.email] = False       # assume the worst, for now

    week = util.existingsnippet_monday(today)
    snippets_q = models.Snippet.all()
    snippets_q.filter('week = ', week)
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

    jinja2_instance = jinja2.get_jinja2()
    mail.send_mail(sender=app_settings.email_from,
                   to=to,
                   subject=subject,
                   body=jinja2_instance.render_template(template_path,
                                                        **template_values))
    # Appengine has a quota of 32 emails per minute:
    #    https://developers.google.com/appengine/docs/quotas#Mail
    # We pause 2 seconds between each email to make sure we
    # don't go over that.
    time.sleep(2)


class SendFridayReminderChat(BaseHandler):
    """Send a chat message to the configured chat room(s)."""

    def get(self):
        msg = 'Reminder: Weekly snippets due Monday at 5pm.'
        _send_to_chat(msg, "/")


class SendReminderEmail(BaseHandler):
    """Send an email to everyone who doesn't have a snippet for this week."""

    def _send_mail(self, email):
        template_values = {}
        _maybe_send_snippets_mail(email, 'Weekly snippets due today at 5pm',
                                  'reminder_email.txt', template_values)

    def get(self):
        email_to_has_snippet = _get_email_to_current_snippet_map(_TODAY_FN())
        for (user_email, has_snippet) in email_to_has_snippet.iteritems():
            if not has_snippet:
                self._send_mail(user_email)
                logging.debug('sent reminder email to %s' % user_email)
            else:
                logging.debug('did not send reminder email to %s: '
                              'has a snippet already' % user_email)

        msg = 'Reminder: Weekly snippets due today at 5pm.'
        _send_to_chat(msg, "/")


class SendViewEmail(BaseHandler):
    """Send an email to everyone to look at the week's snippets."""

    def _send_mail(self, email, has_snippets):
        template_values = {'has_snippets': has_snippets}
        _maybe_send_snippets_mail(email, 'Weekly snippets are ready!',
                                  'view_email.txt', template_values)

    def get(self):
        email_to_has_snippet = _get_email_to_current_snippet_map(_TODAY_FN())
        for (user_email, has_snippet) in email_to_has_snippet.iteritems():
            self._send_mail(user_email, has_snippet)
            logging.debug('sent "view" email to %s' % user_email)

        msg = 'Weekly snippets are ready!'
        _send_to_chat(msg, "/weekly")


application = webapp2.WSGIApplication([
    ('/', UserPage),
    ('/weekly', SummaryPage),
    ('/update_snippet', UpdateSnippet),
    ('/settings', Settings),
    ('/update_settings', UpdateSettings),
    ('/admin/settings', AppSettings),
    ('/admin/update_settings', UpdateAppSettings),
    ('/admin/manage_users', ManageUsers),
    ('/admin/send_friday_reminder_chat', SendFridayReminderChat),
    ('/admin/send_reminder_email', SendReminderEmail),
    ('/admin/send_view_email', SendViewEmail),
    ('/slack', slacklib.SlashCommand),
    ],
    debug=True)
