# -*- coding: utf-8 -*-
"""Snippets server -> Slack integration.

This provides HipChat integration with the snippet server, for
organizations that use Slack for messaging.  This provides Slack
integration with the snippet server, as well prototype CLI style
interaction with snippets via the Slack "slash commands" integration.

Talking to the Slack Web API requires a token.  The admin must enter
the value of this token on /admin/settings.  There are instructions
there for how to do so.

Additionally, the "slash commands" integration in Slack will post a
token with each request.  We check this token for security reasons, so
we get that from /admin/settings as well.
"""

import datetime
import json
import logging
import os
import re
import textwrap
import urllib.error
import urllib.parse
import urllib.request

import flask
from google.appengine.api import memcache

import models
import util

# The Slack slash command token is sent to us by the Slack server with
# every incoming request.  We verify it here for security. To make it
# easier to develop, you can disable the verification step while
# testing.
_REQUIRE_SLASH_TOKEN = True


# This allows mocking in a different day, for testing.
_TODAY_FN = datetime.datetime.now

# The web URL we point people to as the base for web operations
_WEB_URL = 'http://' + os.environ.get('SERVER_NAME', 'localhost')


def _web_api(api_method, payload):
    """Send a payload to the Slack Web API, automatically inserting token.

    Uses AppSettings.slack_token to get the token.  Callers must ensure
    that slack_token exists (or this call will fail).

    Raises a ValueError if something goes wrong.
    Returns a dictionary with the response.
    """
    app_settings = models.AppSettings.get()
    payload.setdefault('token', app_settings.slack_token)
    uri = 'https://slack.com/api/' + api_method
    r = urllib.request.urlopen(uri, urllib.parse.urlencode(payload))

    # check return code for server errors
    if r.getcode() != 200:
        raise ValueError(r.read())
    # parse the JSON...
    # slack web API always returns either `"ok": true` or `"error": "reason"`
    reply = json.loads(r.read())
    if not reply['ok']:
        raise ValueError('Slack error: %s' % reply['error'])
    return reply


def _get_user_email(uid):
    """Retrieve the email address for a specific userid from the Slack Web API.

    Raises ValueError if could not be retrieved.
    """
    reply = _web_api('users.info', {'user': uid})  # possible ValueError
    email = reply.get('user', {}).get('profile', {}).get('email', None)
    if email is None:
        raise ValueError('Slack user profile did not have email')
    return email


def _get_user_email_cached(uid, force_refresh=False):
    """Retrieve the email address for a specific user id, with a cache.

    Results are stored in memcache for up to a day.

    If force_refresh parameter is specified, cached data will be refreshed.

    Raises ValueError if could not be retrieved.
    """
    key = 'slack_profile_email_' + uid
    cached_data = memcache.get(key)
    if (cached_data is None) or force_refresh:
        logging.debug("cache miss/refresh for slack email lookup %s", uid)
        email = _get_user_email(uid)  # possible ValueError
        if not memcache.set(key=key, value=email, time=86400):
            logging.error('memcache set failed!')
        return email
    else:
        logging.debug("cache hit for slack email lookup %s", uid)
        return cached_data


def send_to_slack_channel(channel, msg):
    """Send a plaintext message to a Slack channel."""
    try:
        _web_api('chat.postMessage', {
            'channel': channel,
            'text': msg,
            'username': 'Snippets',
            'icon_emoji': ':pencil:',
            'unfurl_links': False,    # no link previews, please
        })
    except ValueError as why:
        logging.error('Failed sending message to slack: %s', why)


###############################
### SLASH COMMANDS ARE FUN! ###
###############################

def command_usage():
    return textwrap.dedent("""
    /snippets                displays your current snippets
    /snippets list           displays your current snippets
    /snippets last           displays your snippets from last week
    /snippets add [item]     adds an item to your weekly snippets
    /snippets del [n]        removes snippet number N
    /snippets dump           shows your snippets list unformatted
    /snippets help           display this help screen
    """)


def command_help():
    """Return the help string for slash commands."""
    return (
        "I can help you manage your "
        "<{}|weekly snippets>! :pencil:".format(_WEB_URL) +
        command_usage()
    )


def _no_user_error(user_email):
    return (
        "You don't appear to have a snippets account yet!\n"
        "To create one, go to {}\n"
        "We looked for your Slack email address: {}"
        .format(_WEB_URL, user_email)
    )


def _user_snippet(user_email, weeks_back=0):
    """Return the user's most recent Snippet.

    If one doesn't exist, one will be automatically filled from the template
    (but not saved).

    By using the optional `weeks_back` parameter, you can step backwards in
    time. Note that if you go back before the user's *first* snippet, they will
    not be filled (the default filling seems to only go forwardwise in time),
    and an IndexError will be raised.

    Raises an IndexError if requested snippet week comes before user birth.
    Raises ValueError if user couldn't be found.
    """
    account = util.get_user_or_die(user_email)  # can raise ValueError
    user_snips = util.snippets_for_user(user_email)
    logging.debug(
        'User %s got snippets from db: %s', user_email, len(user_snips)
    )

    filled_snips = util.fill_in_missing_snippets(user_snips, account,
                                                 user_email, _TODAY_FN())
    logging.debug(
        'User %s snippets *filled* to: %s', user_email, len(filled_snips)
    )

    index = (-1) - weeks_back
    return filled_snips[index]


def _snippet_items(snippet):
    """Return all markdown items in the snippet text.

    For this we expect it the snippet to contain *nothing* but a markdown list.
    We do not support "indented" list style, only one item per linebreak.

    Raises SyntaxError if snippet not in proper format (e.g. contains
        anything other than a markdown list).
    """
    unformatted = snippet.text and snippet.text.strip()

    # treat null text value as empty list
    if not unformatted:
        return []

    # parse out all markdown list items
    items = re.findall(r'^[-*+] +(.*)$', unformatted, re.MULTILINE)

    # if there were any lines that didn't yield an item, assume there was
    # something we didn't parse. since we never want to lose existing data
    # for a user, this is an error condition.
    if len(items) < len(unformatted.splitlines()):
        raise SyntaxError('unparsed lines in user snippet: %s' % unformatted)

    return items


def _format_snippet_items(items):
    """Format snippet items for display."""
    fi = ['> :pushpin: *[{}]* {}'.format(i, x) for i, x in enumerate(items)]
    return "\n".join(fi)


def command_list(user_email):
    """Return the users current snippets for the week in pretty format."""
    try:
        items = _snippet_items(_user_snippet(user_email))
    except ValueError:
        return _no_user_error(user_email)
    except SyntaxError:
        return (
            "*Your snippets are not in a format I understand.* :cry:\n"
            "I support markdown lists only, "
            "for more information see `/snippets help` ."
        )

    if not items:
        return (
            "*You don't have any snippets for this week yet!* :speak_no_evil:\n"
            ":pencil: Use `/snippets add` to create one, or try "
            "`/snippets help` ."
        )

    return textwrap.dedent(
        "*Your snippets for the week so far:*\n" +
        _format_snippet_items(items)
    )


def command_last(user_email):
    """Return the users snippets for last week in a pretty format."""
    try:
        items = _snippet_items(_user_snippet(user_email, 1))
    except ValueError:
        return _no_user_error(user_email)
    except IndexError:
        return "*You didn't have any snippets last week!* :speak_no_evil:"
    except SyntaxError:
        return (
            "*Your snippets last week are not in a format I understand.* "
            ":cry:\n"
            "I support markdown lists only. "
            "For more information see `/snippets help` ."
        )

    if not items:
        return "*You didn't have any snippets last week!* :speak_no_evil:"

    return textwrap.dedent(
        "*Your snippets for last week:*\n" +
        _format_snippet_items(items)
    )


def _linkify_usernames(text):
    """Slack wants @usernames to be surrounded in <> to be highlighted."""
    return re.sub(r'(?<!<)(@[\w_]+)', r'<\1>', text)


def _markdown_list(items):
    """Transform a list of items into a markdown list."""
    return "\n".join(["- {}".format(x) for x in items])


def command_add(user_email, new_item):
    """Add a new item to the user's current snippet list."""
    if not new_item:
        return (
            ":grey_question: Urm, *what* do you want me to add exactly?\n"
            "Usage: `/snippets add [item]`"
        )

    # TODO(csilvers): move this get/update/put atomic into a txn
    try:
        snippet = _user_snippet(user_email)      # may raise ValueError
        items = _snippet_items(snippet)          # may raise SyntaxError
    except ValueError:
        return _no_user_error(user_email)
    except SyntaxError:
        return (
            "*Your snippets are not in a format I understand.* :cry:\n"
            "So I can't add to them! FYI I support markdown lists only, "
            "for more information see `/snippets help` ."
        )

    new_item = _linkify_usernames(new_item)
    items.append(new_item)
    snippet.text = _markdown_list(items)
    snippet.is_markdown = True

    # TODO(mroth): we should abstract out DB writes to a library wrapper
    snippet.put()
    snippet.key.get()    # ensure db consistency for HRD
    return "Added *{}* to your weekly snippets.".format(new_item)


def command_del(user_email, args):
    """Delete an item at an index from the users current snippets.

    The `args` parameter should be the args passed to the command.  We
    only expect one (for the index) but the user might not pass it, or pass
    extra things (which is an error condition for now).
    """
    syntax_err_msg = (
        ":grey_question: Urm, *what* do you want me to delete exactly?\n"
        "Usage: `/snippets del [n]`"
    )
    if not args or len(args) != 1:
        return syntax_err_msg

    try:
        index = int(args[0])
    except ValueError:
        return syntax_err_msg

    # TODO(csilvers): move this get/update/put atomic into a txn
    try:
        snippet = _user_snippet(user_email)      # may raise ValueError
        items = _snippet_items(snippet)          # may raise SyntaxError
    except ValueError:
        return _no_user_error(user_email)
    except SyntaxError:
        return (
            "*Your snippets are not in a format I understand.* :cry:\n"
            "So I can't delete from them! FYI I support markdown lists only, "
            "for more information see `/snippets help` ."
        )

    try:
        removed_item = items[index]
        del items[index]
    except IndexError:
        return (
            ":grey_question: You don't have anything at that index?!\n" +
            _format_snippet_items(items)
        )

    snippet.text = _markdown_list(items)
    snippet.is_markdown = True

    snippet.put()
    snippet.key.get()    # ensure db consistency for HRD
    return "Removed *{}* from your weekly snippets.".format(removed_item)


def command_dump(user_email):
    """Return user's most recent snippet unformatted."""
    try:
        snippet = _user_snippet(user_email)
    except ValueError:
        return _no_user_error(user_email)
    return "```{}```".format(snippet.text or 'No snippet yet for this week')


def slash_command_handler():
    """Process an incoming slash command from Slack.

    Incoming request POST looks like the following (example taken from
    https://api.slack.com/slash-commands):
        token=gIkuvaNzQIHg97ATvDxqgjtO
        team_id=T0001
        team_domain=example
        channel_id=C2147483705
        channel_name=test
        user_id=U2147483697
        user_name=Steve
        command=/weather
        text=94070
    """
    req, res = flask.request, flask.response

    expected_token = models.AppSettings.get().slack_slash_token

    if not expected_token:
        res.write('Slack slash commands disabled. An admin '
                    'can enable them at /admin/settings')
        return

    # verify slash API post token for security
    if _REQUIRE_SLASH_TOKEN:
        token = req.get('token')
        if token != expected_token:
            logging.error("POST MADE WITH INVALID TOKEN")
            res.write("OH NO YOU DIDNT! Security issue plz contact admin.")
            return


    user_name = req.get('user_name')
    user_id = req.get('user_id')
    text = req.get('text')

    try:
        user_email = _get_user_email_cached(user_id)
    except ValueError:
        logging.error("Failed getting %s email from Slack API", user_name)
        res.write(
            "Error getting your email address from the Slack API! "
            "Please contact an admin and report the time of this error."
        )
        return

    words = text.strip().split()
    if not words:
        logging.info('null (list) command from user %s', user_name)
        res.write(command_list(user_email))
    else:
        cmd, args = words[0], words[1:]
        if cmd == 'help':
            logging.info('help command from user %s', user_name)
            res.write(command_help())
        elif cmd == 'whoami':
            # undocumented command to echo user email back
            logging.info('whoami command from user %s', user_name)
            res.write(user_email)
        elif cmd == 'whoami!':
            # whoami! forces a refresh of cache, for debugging
            logging.info('whoami! command from user %s', user_name)
            logging.info('whoami! potential cached email for %s: %s',
                            user_name, user_email)
            refreshed = _get_user_email_cached(user_id, force_refresh=True)
            logging.info('whoami! refreshed email for %s: %s',
                            user_name, refreshed)
            res.write(refreshed)
        elif cmd == 'list':
            # this is the same as the null command, but support for UX
            logging.info('list command from user %s', user_name)
            res.write(command_list(user_email))
        elif cmd == 'last':
            logging.info('last command from user %s', user_name)
            res.write(command_last(user_email))
        elif cmd == 'add':
            logging.info('add command from user %s', user_name)
            res.write(command_add(user_email, " ".join(args)))
        elif cmd == 'del':
            logging.info('del command from user %s', user_name)
            res.write(command_del(user_email, args))
        elif cmd == 'dump':
            logging.info('dump command from user %s', user_name)
            res.write(command_dump(user_email))
        else:
            logging.info('unknown command %s from user %s', cmd, user_name)
            res.write(
                "I don't understand what you said! "
                "Perhaps you meant one of these?\n```%s```\n"
                % command_usage()
            )
