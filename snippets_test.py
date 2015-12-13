#!/usr/bin/env python

"""Tests for the snippets server.

This tests the functionality found at weekly-snippets.appspot.com.

c.f. http://code.google.com/appengine/docs/python/tools/localunittesting.html
c.f. http://webtest.pythonpaste.org/en/latest/index.html
"""

__author__ = 'Craig Silverstein <csilvers@khanacademy.org>'


import datetime
import os
import re
import sys
import time
try:   # Work under either python2.5 or python2.7
    import unittest2 as unittest
except ImportError:
    import unittest

# Update sys.path so it can find these.  We just need to add
# 'google_appengine', but we add all of $PATH to be easy.  This
# assumes the google_appengine directory is on the path.
sys.path.extend(os.environ['PATH'].split(':'))
import dev_appserver
dev_appserver.fix_sys_path()

from google.appengine.datastore import datastore_stub_util
from google.appengine.ext import db
from google.appengine.ext import testbed
import webtest   # may need to do 'pip install webtest'

import models
import snippets


_TEST_TODAY = datetime.datetime(2012, 2, 23)


class SnippetsTestBase(unittest.TestCase):
    def setUp(self):
        # We're not interested in testing consistency stuff in these tests.
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(
            probability=1)
        self.testbed.init_datastore_v3_stub(consistency_policy=policy)
        self.testbed.init_user_stub()
        self.request_fetcher = webtest.TestApp(snippets.application)
        snippets._TODAY_FN = lambda: _TEST_TODAY

    def tearDown(self):
        self.testbed.deactivate()

    def login(self, email):
        self.testbed.setup_env(user_email=email, overwrite=True)
        self.testbed.setup_env(user_id=email, overwrite=True)
        self.testbed.setup_env(user_is_admin='0', overwrite=True)

    def set_is_admin(self):
        self.testbed.setup_env(user_is_admin='1', overwrite=True)

    def assertNumSnippets(self, body, expected_count):
        """Assert the page 'body' has exactly expected_count snippets in it."""
        # We annotate the div at the beginning of each snippet with
        # class="<etc> unique-snippet".
        self.assertEqual(expected_count, body.count('unique-snippet'),
                         body)

    def _ith_snippet(self, body, snippet_number):
        """For user- and weekly-pages, return the i-th snippet, 0-indexed."""
        # The +1 is because the 0-th element is stuff before the 1st snippet.
        # If we get an IndexError, it means there aren't that many snippets.
        try:
            return body.split('unique-snippet',
                              snippet_number + 2)[snippet_number + 1]
        except IndexError:
            raise IndexError('Has fewer than %d snippets:\n%s'
                             % ((snippet_number + 1), body))

    def assertInSnippet(self, text, body, snippet_number):
        """For snippet-page 'body', assert 'text' is in the i-th snippet.

        This works for both user-pages and weekly-pages -- we figure out
        the boundaries of the snippets, and check whether the text is
        in the given snippet.

        If text is a list or tuple, we check each item of text in turn.

        Arguments:
           text: the text to find in the snippet.  If a list or tuple,
             test each item in the list in turn.
           body: the full html page
           snippet_number: which snippet on the page to examine.
             Index starts at 0.
        """
        self.assertIn(text, self._ith_snippet(body, snippet_number))

    def assertNotInSnippet(self, text, body, snippet_number):
        """For snippet-page 'body', assert 'text' is not in the ith snippet."""
        self.assertNotIn(text, self._ith_snippet(body, snippet_number))


class UserTestBase(SnippetsTestBase):
    """The most common base: someone who is logged in as user@example.com."""
    def setUp(self):
        super(UserTestBase, self).setUp()
        self.login('user@example.com')


class PostTestCase(SnippetsTestBase):
    """test the correct output from the server when POSTing"""

    def testPostSnippet(self):
        self.login('user@example.com')
        url = '/update_snippet'
        params = {
            'week': '02-20-2012',
            'snippet': 'my inspired snippet'
        }
        response = self.request_fetcher.post(url, params, status=200)
        self.assertIn('{"status": 200, "message": "ok"}', response)

    def testPostSnippetAsOtherPerson(self):
        self.login('user@example.com')
        url = '/update_snippet'
        params = {
            'week': '02-20-2012',
            'snippet': 'my fallacious snippet',
            'u': 'joeuser@example.com'
        }
        response = self.request_fetcher.post(url, params, status=403)
        self.assertIn('"status": 403', response)
        self.assertIn('joeuser@example.com', response)

    def testPostSnippetNotLoggedIn(self):
        url = '/update_snippet'
        params = {
            'week': '02-20-2012',
            'snippet': 'my fallacious snippet',
            'u': 'user@example.com'
        }
        response = self.request_fetcher.post(url, params, status=403)
        self.assertIn('"status": 403', response)
        self.assertIn('"message": "not logged in"', response)

    def testPostSnippetIsolation(self):
        # updating a single snippet via POST should not affect other snippets
        self.login('user@example.com')

        # create three snippets
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-27-2012&snippet=my+second+snippet'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=03-05-2012&snippet=my+third+snippet'
        self.request_fetcher.get(url)

        # update only middle snippet
        url = '/update_snippet'
        params = {
            'week': '02-27-2012',
            'snippet': 'updated second snippet'
        }
        self.request_fetcher.post(url, params, status=200)

        # make sure only the second snippet changed
        response = self.request_fetcher.get('/')
        self.assertInSnippet('>my third snippet<', response.body, 0)
        self.assertInSnippet('>updated second snippet<', response.body, 1)
        self.assertNotInSnippet('>my second snippet<', response.body, 1)
        self.assertInSnippet('>my snippet<', response.body, 2)


class LoginRequiredTestCase(SnippetsTestBase):
    def assert_requires_login(self, response):
        """Assert that a response causes us to redirect to the login page."""
        self.assertIn('login', response.headers.get('Location', '').lower())

    def assert_does_not_require_login(self, response):
        """Assert that a response is not a redirect to the login page."""
        self.assertNotIn('login', response.headers.get('Location', '').lower())

    def testLoginRequiredForUserView(self):
        url = '/'
        response = self.request_fetcher.get(url)
        self.assert_requires_login(response)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assert_does_not_require_login(response)

    def testLoginRequiredForWeeklyView(self):
        url = '/weekly'
        response = self.request_fetcher.get(url)
        self.assert_requires_login(response)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assert_does_not_require_login(response)

    def testLoginRequiredForSettingsView(self):
        url = '/settings'
        response = self.request_fetcher.get(url)
        self.assert_requires_login(response)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assert_does_not_require_login(response)

    def testLoginRequiredToUpdateSnippet(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        response = self.request_fetcher.get(url)
        self.assert_requires_login(response)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assert_does_not_require_login(response)

    def testLoginRequiredToUpdateSettings(self):
        url = '/update_settings'
        response = self.request_fetcher.get(url)
        self.assert_requires_login(response)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assert_does_not_require_login(response)


class AccessTestCase(UserTestBase):
    """Tests that you can't modify someone who is not yourself."""

    def testCanViewOtherSnippets(self):
        url = '/?u=notuser@example.com'
        # Raises an error if we don't get a 200 response.
        self.request_fetcher.get(url)

    def testCanViewWeeklyPage(self):
        """u is ignored for /weekly, but included for completeness."""
        url = '/weekly?u=notuser@example.com'
        self.request_fetcher.get(url)

    def testCannotEditOtherSnippets(self):
        url = ('/update_snippet?week=02-20-2012&snippet=my+snippet'
               '&u=notuser@example.com')
        # Raises an error if we don't get a 500 response (meaning no perm).
        self.request_fetcher.get(url, status=500)

    def testCannotViewOtherSettings(self):
        url = '/settings?u=notuser@example.com'
        self.request_fetcher.get(url, status=500)

    def testCannotEditOtherSettings(self):
        url = '/update_settings?u=notuser@example.com'
        self.request_fetcher.get(url, status=500)

    def testCanEditOwnSnippets(self):
        url = ('/update_snippet?week=02-20-2012&snippet=my+snippet'
               '&u=user@example.com')
        self.request_fetcher.get(url)

    def testCanViewOwnSettings(self):
        url = '/settings?u=user@example.com'
        self.request_fetcher.get(url)

    def testCanEditOwnSettings(self):
        url = '/update_settings?u=user@example.com'
        self.request_fetcher.get(url)

    def testCanEditOtherSnippetsAsAdmin(self):
        self.set_is_admin()
        url = ('/update_snippet?week=02-20-2012&snippet=my+snippet'
               '&u=notuser@example.com')
        self.request_fetcher.get(url)

    def testCanViewOtherSettingsAsAdmin(self):
        self.set_is_admin()
        url = '/settings?u=notuser@example.com'
        self.request_fetcher.get(url)

    def testCanEditOtherSettingsAsAdmin(self):
        self.set_is_admin()
        url = '/update_settings?u=notuser@example.com'
        self.request_fetcher.get(url)


class NewUserTestCase(UserTestBase):
    """Test the workflow for registering as a new user."""

    def testNewUserLogin(self):
        response = self.request_fetcher.get('/')
        self.assertIn('<title>New user</title>', response.body)

    def testNewUserContinueUrl(self):
        """After verifying settings, we should go back to snippet-entry."""
        response = self.request_fetcher.get('/')
        m = re.search(r'<a href="(/settings[^"]*)">', response.body)
        continue_url = m.group(1)

        settings_response = self.request_fetcher.get(continue_url)
        self.assertIn('name="redirect_to" value="snippet_entry"',
                      settings_response.body)

        # Now kinda-simulate clicking on the submit button
        done_response = self.request_fetcher.get(
            '/update_settings?u=user@example.com&redirect_to=snippet_entry')
        if done_response.status_int in (301, 302, 303, 304):
            done_response = done_response.follow()
        self.assertIn('Snippets for user@example.com', done_response.body)


class UserSettingsTestCase(UserTestBase):
    """Test that user settings flow through to snippets page appropriately."""

    def assertInputIsChecked(self, name, body, snippet_number):
        self.assertRegexpMatches(body, r'name="%s" value="True"\s+checked\s*>'
                                 % name, snippet_number)

    def assertInputIsNotChecked(self, name, body, snippet_number):
        self.assertRegexpMatches(body, r'name="%s" value="True"\s*>' % name,
                                 snippet_number)

    def testDefaultUserSettings(self):
        # Make sure the rest of the tests are actually testing
        # non-default behavior.
        self.request_fetcher.get('/update_settings?u=user@example.com')

        response = self.request_fetcher.get('/')
        # Neither private nor 'is-markdown' are checked by default.
        self.assertInputIsNotChecked('private', response.body, 0)
        self.assertInputIsNotChecked('is_markdown', response.body, 0)

    def testPrivateUser(self):
        self.request_fetcher.get(
            '/update_settings?u=user@example.com&private=yes')
        response = self.request_fetcher.get('/')
        self.assertInputIsChecked('private', response.body, 0)
        self.assertInputIsNotChecked('is_markdown', response.body, 0)

    def testMarkdownUser(self):
        self.request_fetcher.get(
            '/update_settings?u=user@example.com&markdown=yes')
        response = self.request_fetcher.get('/')
        self.assertInputIsNotChecked('private', response.body, 0)
        self.assertInputIsChecked('is_markdown', response.body, 0)

    def testSettingsForFilledInSnippets(self):
        url = '/update_snippet?week=02-21-2011&snippet=old+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 53)
        self.assertInSnippet('(No snippet for this week)', response.body, 9)
        self.assertInputIsNotChecked('private', response.body, 9)
        self.assertInputIsNotChecked('is_markdown', response.body, 9)
        self.assertInSnippet('old snippet', response.body, 52)
        self.assertInputIsNotChecked('private', response.body, 52)
        self.assertInputIsNotChecked('is_markdown', response.body, 52)

        self.request_fetcher.get(
            '/update_settings?u=user@example.com&markdown=yes')
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 53)
        self.assertInSnippet('(No snippet for this week)', response.body, 9)
        self.assertInputIsNotChecked('private', response.body, 9)
        self.assertInputIsChecked('is_markdown', response.body, 9)
        # But the existing snippet is unaffected.
        self.assertInSnippet('old snippet', response.body, 52)
        self.assertInputIsNotChecked('private', response.body, 52)
        self.assertInputIsNotChecked('is_markdown', response.body, 52)

        self.request_fetcher.get(
            '/update_settings?u=user@example.com&private=yes')
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 53)
        self.assertInSnippet('(No snippet for this week)', response.body, 9)
        self.assertInputIsChecked('private', response.body, 9)
        self.assertInputIsNotChecked('is_markdown', response.body, 9)
        self.assertInSnippet('old snippet', response.body, 52)
        self.assertInputIsNotChecked('private', response.body, 52)
        self.assertInputIsNotChecked('is_markdown', response.body, 52)

    def testCategoryUnset(self):
        self.request_fetcher.get('/update_settings?u=user@example.com')
        response = self.request_fetcher.get('/')
        self.assertInSnippet('WARNING: Snippet will go in the "(unknown)"',
                             response.body, 0)

    def testCategorySet(self):
        self.request_fetcher.get('/update_settings?u=user@example.com')
        self.request_fetcher.get(
            '/update_settings?u=user@example.com&category=Dev')
        response = self.request_fetcher.get('/')
        self.assertNotInSnippet('WARNING: Snippet will go in the "(unknown)"',
                                response.body, 0)

    def testCategoryUnsetButSnippetHasContent(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/')
        self.assertNotInSnippet('WARNING: Snippet will go in the "(unknown)"',
                                response.body, 0)

    def testCategoryCheckForFilledInSnippets(self):
        url = '/update_snippet?week=02-21-2011&snippet=old+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 53)
        self.assertInSnippet('(No snippet for this week)', response.body, 9)
        self.assertInSnippet('WARNING: Snippet will go in the "(unknown)"',
                             response.body, 9)
        self.assertInSnippet('old snippet', response.body, 52)
        self.assertNotInSnippet('WARNING: Snippet will go in the "(unknown)"',
                                response.body, 52)

    def testHiddenUser(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 1)
        response = self.request_fetcher.get('/weekly?week=02-27-2012')
        self.assertNumSnippets(response.body, 1)    # "no snippet this week"

        url = '/update_settings?u=user@example.com&is_hidden=yes'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        # Hiding doesn't affect the user-snippets page, just the weekly one.
        self.assertNumSnippets(response.body, 1)
        response = self.request_fetcher.get('/weekly?week=02-27-2012')
        self.assertNumSnippets(response.body, 0)
        # And it doesn't affect existing snippets, just empty ones.
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 1)

    def testNewSnippetUnhides(self):
        url = '/update_snippet?week=02-13-2012&snippet=my+snippet'
        self.request_fetcher.get(url)

        url = '/update_settings?u=user@example.com&is_hidden=yes'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 0)

        url = '/update_snippet?week=02-27-2012&snippet=new+snippet'
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 1)
        response = self.request_fetcher.get('/weekly?week=02-27-2012')
        self.assertNumSnippets(response.body, 1)

    def testChangingSettingsUnhides(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)

        url = '/update_settings?u=user@example.com&is_hidden=yes'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/weekly?week=02-27-2012')
        self.assertNumSnippets(response.body, 0)

        url = '/update_settings?u=user@example.com'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/weekly?week=02-27-2012')
        self.assertNumSnippets(response.body, 1)


class SetAndViewSnippetsTestCase(UserTestBase):
    """Set some snippets, then make sure they're viewable."""

    def testSetAndViewInUserMode(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('>my snippet<', response.body, 0)

    def testSetAndViewInWeeklyMode(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('>my snippet<', response.body, 0)

    def testCannotSeeInOtherWeek(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(no snippet this week)', response.body, 0)
        self.assertNotIn('>my snippet<', response.body)

    def testViewSnippetsForTwoUsers(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        self.login('other@example.com')
        url = '/update_snippet?week=02-20-2012&snippet=other+snippet'
        self.request_fetcher.get(url)

        # This is done as other
        response = self.request_fetcher.get('/')
        self.assertIn('other@example.com', response.body)
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('>other snippet<', response.body, 0)
        self.assertNotIn('user@example.com', response.body)
        self.assertNotIn('>my snippet<', response.body)
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 2)
        self.assertInSnippet('other@example.com', response.body, 0)
        self.assertInSnippet('>other snippet<', response.body, 0)
        self.assertInSnippet('user@example.com', response.body, 1)
        self.assertInSnippet('>my snippet<', response.body, 1)

        # This is done as user
        self.login('user@example.com')
        response = self.request_fetcher.get('/')
        self.assertIn('user@example.com', response.body)
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('>my snippet<', response.body, 0)
        self.assertNotIn('other@example.com', response.body)
        self.assertNotIn('>other snippet<', response.body)
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 2)
        self.assertInSnippet('other@example.com', response.body, 0)
        self.assertInSnippet('>other snippet<', response.body, 0)
        self.assertInSnippet('user@example.com', response.body, 1)
        self.assertInSnippet('>my snippet<', response.body, 1)

    def testViewSnippetsForTwoWeeks(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-27-2012&snippet=my+second+snippet'
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 2)
        # Snippets go in reverse chronological order (i.e. newest first)
        self.assertInSnippet('>my second snippet<', response.body, 0)
        self.assertInSnippet('>my snippet<', response.body, 1)

        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('user@example.com', response.body, 0)
        self.assertInSnippet('>my snippet<', response.body, 0)
        self.assertNotIn('>my second snippet<', response.body)

        response = self.request_fetcher.get('/weekly?week=02-27-2012')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('user@example.com', response.body, 0)
        self.assertInSnippet('>my second snippet<', response.body, 0)
        self.assertNotIn('>my snippet<', response.body)

        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(no snippet this week)', response.body, 0)
        self.assertNotIn('>my snippet<', response.body)
        self.assertNotIn('>my second snippet<', response.body)

    def testViewEmptySnippetsInWeekMode(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        self.login('other@example.com')
        url = '/update_snippet?week=02-27-2012&snippet=other+snippet'
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 2)
        # Other-user comes first alphabetically.
        self.assertInSnippet('other@example.com', response.body, 0)
        self.assertInSnippet('(no snippet this week)', response.body, 0)
        self.assertInSnippet('user@example.com', response.body, 1)
        self.assertInSnippet('>my snippet<', response.body, 1)

        response = self.request_fetcher.get('/weekly?week=02-27-2012')
        self.assertNumSnippets(response.body, 2)
        self.assertInSnippet('other@example.com', response.body, 0)
        self.assertInSnippet('>other snippet<', response.body, 0)
        self.assertInSnippet('user@example.com', response.body, 1)
        self.assertInSnippet('(no snippet this week)', response.body, 1)

    def testViewEmptySnippetsInUserMode(self):
        """Occurs when there's a gap between two snippets."""
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-06-2012&snippet=my+old+snippet'
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 3)
        self.assertInSnippet('>my snippet<', response.body, 0)
        self.assertInSnippet('(No snippet for this week)', response.body, 1)
        self.assertInSnippet('>my old snippet<', response.body, 2)

    def testCategorizeSnippets(self):
        """Weekly view should sort based on user categories."""
        # I give the users numeric names to make it easy to see sorting.
        self.login('2@example.com')
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        url = '/update_settings?category=a+1st'
        self.request_fetcher.get(url)

        self.login('3@example.com')
        url = '/update_snippet?week=02-20-2012&snippet=also+snippet'
        self.request_fetcher.get(url)
        url = '/update_settings?category=a+1st'
        self.request_fetcher.get(url)

        self.login('1@example.com')
        url = '/update_snippet?week=02-20-2012&snippet=late+snippet'
        self.request_fetcher.get(url)
        url = '/update_settings?category=b+2nd'
        self.request_fetcher.get(url)

        self.login('4@example.com')
        url = '/update_snippet?week=02-20-2012&snippet=late+snippet'
        self.request_fetcher.get(url)

        # Order should be 4 ((unknown) category), 2 and 3 (a 1st) and
        # then 1 (b 2nd).
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 4)
        self.assertInSnippet('4@example.com', response.body, 0)
        self.assertInSnippet('2@example.com', response.body, 1)
        self.assertInSnippet('3@example.com', response.body, 2)
        self.assertInSnippet('1@example.com', response.body, 3)

    def testViewSnippetAfterAUserIsDeleted(self):
        """When a user is deleted, their snippet should still show up."""
        self.login('2@example.com')
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        self.request_fetcher.get(url)
        url = '/update_settings?category=a+1st'
        self.request_fetcher.get(url)

        # Now delete user 2
        u = models.User.all().filter('email =', '2@example.com').get()
        u.delete()

        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('2@example.com', response.body, 0)
        self.assertTrue('(unknown)' in response.body)

    def testWarningsWhenDue(self):
        url = '/update_snippet?week=02-06-2012&snippet=old+snippet'
        self.request_fetcher.get(url)

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 19)
        response = self.request_fetcher.get('/')
        self.assertNotIn('Due today', response.body)
        self.assertNotIn('OVERDUE', response.body)

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 20)
        response = self.request_fetcher.get('/')
        self.assertIn('Due today', response.body)
        self.assertNotIn('OVERDUE', response.body)

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 21)
        response = self.request_fetcher.get('/')
        self.assertNotIn('Due today', response.body)
        self.assertIn('OVERDUE', response.body)

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 22)
        response = self.request_fetcher.get('/')
        self.assertNotIn('Due today', response.body)
        self.assertNotIn('OVERDUE', response.body)

    def testWarningsWhenNotDue(self):
        url = '/update_snippet?week=02-13-2012&snippet=my+snippet'
        self.request_fetcher.get(url)

        for date in (19, 20, 21, 22):
            snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, date)
            response = self.request_fetcher.get('/')
            self.assertNotIn('Due today', response.body)
            self.assertNotIn('OVERDUE', response.body)

    def testPrettyDateFormatting(self):
        # Just so we're not a new user.
        url = '/update_snippet?week=02-06-2012&snippet=my+snippet'
        self.request_fetcher.get(url)

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 6)
        response = self.request_fetcher.get('/')
        self.assertIn('February 6, 2012', response.body)

    def testUrlize(self):
        url = '/update_snippet?week=02-20-2012&snippet=visit+http://foo.com'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet(
            '>visit <a href="http://foo.com">http://foo.com</a><',
            response.body, 0)

        # Also make sure we urlize on the user page.
        self.login('2@example.com')
        response = self.request_fetcher.get('/?u=user@example.com')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet(
            '>visit <a href="http://foo.com">http://foo.com</a><',
            response.body, 0)

    def testEditMode(self):
        url = '/update_snippet?week=02-20-2012&snippet=hello'
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/?u=user@example.com')
        self.assertIn('Make snippet private', response.body)

        response = self.request_fetcher.get('/?u=user@example.com&edit=1')
        self.assertIn('Make snippet private', response.body)

        response = self.request_fetcher.get('/?u=user@example.com&edit=0')
        self.assertNotIn('Make snippet private', response.body)


class ShowCorrectWeekTestCase(UserTestBase):
    """Test we show the right snippets for edit/view based on day of week."""

    def setUp(self):
        super(ShowCorrectWeekTestCase, self).setUp()
        # Register the user so snippet-fetching works.
        url = '/update_settings?category=dummy'
        self.request_fetcher.get(url)

    def testMonday(self):
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 20)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        # For *viewing*'s snippets, we always show last week's snippets.
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testTuesday(self):
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 21)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testWednesday(self):
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 22)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testThursday(self):
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 23)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testFriday(self):
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 24)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testSaturday(self):
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 25)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testSunday(self):
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 26)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)


class NosnippetGapFillingTestCase(UserTestBase):
    """Test we show correct text when folks miss a week for snippets."""

    def testNoSnippets(self):
        # If nobody is registered, the user-db will be empty.
        response = self.request_fetcher.get('/weekly')
        self.assertNumSnippets(response.body, 0)

        url = '/update_settings?category=dummy'   # register the user
        self.request_fetcher.get(url)

        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(No snippet for this week)', response.body, 0)

    def testOneSnippetInDistantPast(self):
        url = '/update_snippet?week=02-21-2011&snippet=old+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 53)
        self.assertInSnippet('(No snippet for this week)', response.body, 0)
        self.assertInSnippet('(No snippet for this week)', response.body, 20)
        self.assertInSnippet('(No snippet for this week)', response.body, 50)
        self.assertInSnippet('old snippet', response.body, 52)

        response = self.request_fetcher.get('/weekly')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(no snippet this week)', response.body, 0)

    def testTwoSnippetsInDistantPast(self):
        url = '/update_snippet?week=08-22-2011&snippet=oldish+snippet'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-21-2011&snippet=old+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 53)
        self.assertInSnippet('(No snippet for this week)', response.body, 0)
        self.assertInSnippet('(No snippet for this week)', response.body, 50)
        self.assertInSnippet('oldish snippet', response.body, 26)
        self.assertInSnippet('old snippet', response.body, 52)

        response = self.request_fetcher.get('/weekly')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(no snippet this week)', response.body, 0)

    def testSnippetInTheFuture(self):
        url = '/update_snippet?week=02-18-2013&snippet=future+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('future snippet', response.body, 0)

        response = self.request_fetcher.get('/weekly')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(no snippet this week)', response.body, 0)

    def testSnippetInThePastAndFuture(self):
        url = '/update_snippet?week=02-21-2011&snippet=old+snippet'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-18-2013&snippet=future+snippet'
        self.request_fetcher.get(url)
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 105)
        self.assertInSnippet('future snippet', response.body, 0)
        self.assertInSnippet('(No snippet for this week)', response.body, 52)
        self.assertInSnippet('old snippet', response.body, 104)

        response = self.request_fetcher.get('/weekly')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(no snippet this week)', response.body, 0)


class PrivateSnippetTestCase(UserTestBase):
    """Tests that we properly restrict viewing of private snippets."""

    def setUp(self):
        super(PrivateSnippetTestCase, self).setUp()
        # Set up a user with some private and some not-private snippets,
        # another user with only private, and another with only public.
        self.login('private@example.com')
        url = '/update_snippet?week=02-13-2012&snippet=no+see+um&private=True'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-20-2012&snippet=no+see+um2&private=True'
        self.request_fetcher.get(url)

        self.login('public@example.com')
        url = '/update_snippet?week=02-13-2012&snippet=see+me!'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-20-2012&snippet=see+me+2!'
        self.request_fetcher.get(url)

        self.login('mixed@example.com')
        url = '/update_snippet?week=02-13-2012&snippet=cautious&private=True'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-20-2012&snippet=not+cautious'
        self.request_fetcher.get(url)

        self.login('private@some_other_domain.com')
        url = '/update_snippet?week=02-13-2012&snippet=foreign&private=True'
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-20-2012&snippet=foreign2&private=True'
        self.request_fetcher.get(url)

        self.login('user@example.com')   # back to the normal user

    def testAdminCanSeeAllSnippets(self):
        self.set_is_admin()
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertNumSnippets(response.body, 4)
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 4)

    def testUserCanSeeAllSnippetsFromTheirDomain(self):
        # As user@example.com, we can see all but some_other_domain.com
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        # For private@some_other_domain.com, we should see 'no snippet found'.
        self.assertNumSnippets(response.body, 4)
        self.assertInSnippet('private@some_other_domain.com', response.body, 2)
        self.assertNotInSnippet('foreign', response.body, 2)
        # We *should* see stuff from our domain, but in gray.
        self.assertInSnippet('private@example.com', response.body, 1)
        self.assertInSnippet('private_snippet', response.body, 1)
        self.assertInSnippet('no see um', response.body, 1)
        # And we should see public snippets, not in gray.
        self.assertInSnippet('public@example.com', response.body, 3)
        self.assertNotInSnippet('private_snippet', response.body, 3)
        self.assertInSnippet('see me', response.body, 3)

        self.login('random@some_other_domain.com')
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertNumSnippets(response.body, 4)
        self.assertInSnippet('private@some_other_domain.com', response.body, 2)
        self.assertInSnippet('foreign', response.body, 2)
        self.assertInSnippet('private_snippet', response.body, 2)
        # Now we shouldn't see stuff from example.com
        self.assertInSnippet('private@example.com', response.body, 1)
        self.assertNotInSnippet('no see um', response.body, 1)
        # And we should also see public snippets, not in gray.
        self.assertInSnippet('public@example.com', response.body, 3)
        self.assertNotInSnippet('private_snippet', response.body, 3)
        self.assertInSnippet('see me', response.body, 3)

    def testPrivacyIsPerSnippet(self):
        self.login('random@some_other_domain.com')
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertNumSnippets(response.body, 4)
        self.assertInSnippet('mixed@example.com', response.body, 0)
        self.assertNotInSnippet('cautious', response.body, 0)

        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertNumSnippets(response.body, 4)
        self.assertInSnippet('mixed@example.com', response.body, 0)
        self.assertInSnippet('not cautious', response.body, 0)

    def testDomainMatching(self):
        self.login('close@example.comm')
        url = '/update_snippet?week=02-13-2012&snippet=whoa+comm&private=True'
        self.request_fetcher.get(url)

        self.login('close@example.co')
        url = '/update_snippet?week=02-13-2012&snippet=whoa+co&private=True'
        self.request_fetcher.get(url)

        self.login('close@my-example.com')
        url = '/update_snippet?week=02-13-2012&snippet=whoa+my-&private=True'
        self.request_fetcher.get(url)

        self.login('close@ample.com')
        url = '/update_snippet?week=02-13-2012&snippet=whoa+ample&private=True'
        self.request_fetcher.get(url)

        self.login('user@example.com')
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertNumSnippets(response.body, 8)
        for i in (0, 1, 2, 3):    # the 4 close@ snippets should sort first
            self.assertInSnippet('close@', response.body, i)
            self.assertNotInSnippet('whoa', response.body, i)


class MarkdownSnippetTestCase(UserTestBase):
    """Tests that we properly render snippets using markdown (or not).

    Sadly, the actual markdown is done in javascript, so the best we
    can test here is that the content is marked with the appropriate
    class.
    """
    def setUp(self):
        super(MarkdownSnippetTestCase, self).setUp()

        # Set up some snippets as markdown, and some not.
        url = ('/update_snippet?week=02-13-2012&snippet=*+item+1%0A*+item+2'
               '&is_markdown=True')
        self.request_fetcher.get(url)
        url = '/update_snippet?week=02-20-2012&snippet=*+item+3%0A*+item+4'
        self.request_fetcher.get(url)

    def testMarkdownRendering(self):
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertInSnippet('class="markdown_snippet', response.body, 0)

    def testTextRendering(self):
        response = self.request_fetcher.get('/weekly?week=02-20-2012')
        self.assertInSnippet('class="text_snippet', response.body, 0)


class ManageUsersTestCase(UserTestBase):
    """Test we can delete users properly."""
    def setUp(self):
        super(ManageUsersTestCase, self).setUp()

        # Have users with various snippet characteristics.
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 20, 12, 0, 0)
        self.login('has_one_snippet@example.com')
        self.request_fetcher.get('/update_snippet?week=02-13-2012&snippet=s1')

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 20, 12, 0, 1)
        self.login('has_many_snippets@example.com')
        self.request_fetcher.get('/update_snippet?week=01-30-2012&snippet=s2')
        self.request_fetcher.get('/update_snippet?week=02-13-2012&snippet=s3')

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 20, 12, 0, 2)
        self.login('has_old_snippet@example.com')
        self.request_fetcher.get('/update_snippet?week=02-14-2011&snippet=s4')

        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 20, 12, 0, 3)
        self.login('has_no_snippets@example.com')
        self.request_fetcher.get('/settings')

    def get_user_list(self, body):
        """Returns the email usernames of the user-list, in order."""
        return re.findall(r'name="delete ([^@]*)@example.com"', body)

    def testMustBeAdminToManageUsers(self):
        # Don't know how to test this -- it's enforced by app.yaml
        pass

    def testSortByEmail(self):
        response = self.request_fetcher.get('/admin/manage_users'
                                            '?sort_by=email')
        expected = ['has_many_snippets', 'has_no_snippets',
                    'has_old_snippet', 'has_one_snippet']
        self.assertEqual(expected, self.get_user_list(response.body))
        self.assertNotIn('@example.com deleted', response.body)  # we didn't

    def testSortByCreation(self):
        response = self.request_fetcher.get('/admin/manage_users'
                                            '?sort_by=creation_time')
        # Reverse order from when we created them above.
        expected = ['has_no_snippets', 'has_old_snippet',
                    'has_many_snippets', 'has_one_snippet']
        self.assertEqual(expected, self.get_user_list(response.body))
        self.assertNotIn('@example.com deleted', response.body)  # we didn't

    def testSortByLastSnippet(self):
        response = self.request_fetcher.get('/admin/manage_users'
                                            '?sort_by=last_snippet_time')
        # 'many' and 'one' are tied; the tiebreak is email.
        expected = ['has_no_snippets', 'has_old_snippet',
                    'has_many_snippets', 'has_one_snippet']
        self.assertEqual(expected, self.get_user_list(response.body))
        self.assertNotIn('@example.com deleted', response.body)  # we didn't

    def testBadSortBy(self):
        # status=500 means we expect to get back a 500 error for this.
        self.request_fetcher.get('/admin/manage_users?sort_by=unknown',
                                 status=500)

    def testDelete(self):
        response = self.request_fetcher.get(
            '/admin/manage_users?delete+has_old_snippet@example.com=Delete')
        if response.status_int in (301, 302, 303, 304):
            response = response.follow()

        expected = ['has_no_snippets', 'has_many_snippets', 'has_one_snippet']
        self.assertEqual(expected, self.get_user_list(response.body))
        self.assertIn('has_old_snippet@example.com deleted', response.body)

    def testHide(self):
        response = self.request_fetcher.get(
            '/admin/manage_users?hide+has_old_snippet@example.com=Hide')
        if response.status_int in (301, 302, 303, 304):
            response = response.follow()

        expected = ['has_no_snippets', 'has_old_snippet',
                    'has_many_snippets', 'has_one_snippet']
        self.assertEqual(expected, self.get_user_list(response.body))
        self.assertIn('has_old_snippet@example.com hidden', response.body)
        self.assertIn('value="Unhide"', response.body)

    def testPreserveSortBy(self):
        response = self.request_fetcher.get(
            '/admin/manage_users?hide+has_old_snippet@example.com=Hide'
            '&sort_by=last_snippet_time')
        if response.status_int in (301, 302, 303, 304):
            response = response.follow()

        # "Last snippet" shouldn't have a link letting you sort by
        # last snippet, because it should already be doing so!
        self.assertIn('<th>Last snippet</th>', response.body)

    def testUnhide(self):
        self.request_fetcher.get(
            '/admin/manage_users?hide+has_old_snippet@example.com=Hide')
        response = self.request_fetcher.get(
            '/admin/manage_users?unhide+has_old_snippet@example.com=Hide')
        if response.status_int in (301, 302, 303, 304):
            response = response.follow()

        expected = ['has_no_snippets', 'has_old_snippet',
                    'has_many_snippets', 'has_one_snippet']
        self.assertEqual(expected, self.get_user_list(response.body))
        self.assertIn('has_old_snippet@example.com unhidden', response.body)
        self.assertNotIn('value="Unhide"', response.body)

    def testInvalidButton(self):
        self.request_fetcher.get('/admin/manage_users'
                                 '?delete+has_old_snippet=Delete',
                                 status=500)
        self.request_fetcher.get('/admin/manage_users'
                                 '?hide+has_old_snippet=Hide',
                                 status=500)
        self.request_fetcher.get('/admin/manage_users'
                                 '?unhide+has_old_snippet=Unhide',
                                 status=500)


class SendingEmailTestCase(UserTestBase):
    """Test we correctly send cron emails."""

    def setUp(self):
        super(SendingEmailTestCase, self).setUp()
        self.testbed.init_mail_stub()
        self.mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)
        # Also make sure we suppress sending to hipchat for tests.
        snippets._SEND_TO_HIPCHAT = False
        # The email-senders sleep 2 seconds between sends for quota
        # reasons.  We don't want that for most tests, so we suppress
        # it.  The quota test will redefine time.sleep itself.
        self.sleep_fn = time.sleep
        time.sleep = lambda sec: sec

        # We send out mail on Sunday nights and Monday mornings, so
        # we'll set 'today' to be Sunday right around midnight.
        snippets._TODAY_FN = lambda: datetime.datetime(2012, 2, 19, 23, 50, 0)

        # For our mail tests, we set up a db with a few users, some of
        # whom have snippets for this week ('this week' being 13 Feb
        # 2012), some of whom don't.
        self.login('has_snippet@example.com')
        self.request_fetcher.get('/update_snippet?week=02-13-2012&snippet=s1')

        self.login('has_many_snippets@example.com')
        self.request_fetcher.get('/update_snippet?week=01-30-2012&snippet=s2')
        self.request_fetcher.get('/update_snippet?week=02-13-2012&snippet=s3')

        self.login('does_not_have_snippet@example.com')
        self.request_fetcher.get('/update_snippet?week=01-30-2012&snippet=s4')

        self.login('has_no_snippets@example.com')
        self.request_fetcher.get('/settings')

        self.login('user@example.com')        # back to the normal user

    def tearDown(self):
        UserTestBase.tearDown(self)
        time.sleep = self.sleep_fn

    def assertEmailSentTo(self, email):
        r = self.mail_stub.get_sent_messages(to=email)
        self.assertEqual(1, len(r), r)

    def assertEmailNotSentTo(self, email):
        r = self.mail_stub.get_sent_messages(to=email)
        self.assertEqual(0, len(r), r)

    def assertEmailContains(self, email, text):
        r = self.mail_stub.get_sent_messages(to=email)
        self.assertEqual(1, len(r), r)
        self.assertIn(text, r[0].body.decode())

    def assertEmailDoesNotContain(self, email, text):
        r = self.mail_stub.get_sent_messages(to=email)
        self.assertEqual(1, len(r), r)
        self.assertNotIn(text, r[0].body.decode())

    def testMustBeAdminToSendMail(self):
        # Don't know how to test this -- it's enforced by app.yaml
        pass

    def testSendReminderEmail(self):
        self.request_fetcher.get('/admin/send_reminder_email')
        self.assertEmailSentTo('does_not_have_snippet@example.com')
        self.assertEmailSentTo('has_no_snippets@example.com')
        self.assertEmailNotSentTo('has_snippet@example.com')
        self.assertEmailNotSentTo('has_many_snippets@example.com')
        r = self.mail_stub.get_sent_messages(to='has_no_snippets@example.com')
        self.assertEqual('has_no_snippets@example.com', r[0].to)
        self.assertIn('Snippet Server', r[0].sender)
        self.assertEqual('Weekly snippets due today at 5pm', r[0].subject)

    def testSendViewEmail(self):
        self.request_fetcher.get('/admin/send_view_email')
        self.assertEmailSentTo('has_snippet@example.com')
        self.assertEmailSentTo('does_not_have_snippet@example.com')
        self.assertEmailSentTo('has_many_snippets@example.com')
        self.assertEmailSentTo('has_no_snippets@example.com')
        # Check that we nag the ones who don't have snippets.
        self.assertEmailDoesNotContain('has_snippet@example.com',
                                       'not too late')
        self.assertEmailDoesNotContain('has_many_snippets@example.com',
                                       'not too late')
        self.assertEmailContains('does_not_have_snippet@example.com',
                                 'not too late')
        self.assertEmailContains('has_no_snippets@example.com',
                                 'not too late')

    def testViewReminderMailsSettingAndSendReminderEmail(self):
        """Tests the user config-setting for getting emails."""
        self.login('does_not_have_snippet@example.com')
        self.request_fetcher.get('/update_settings?reminder_email=no')

        # The control group :-)
        self.login('has_no_snippets@example.com')
        self.request_fetcher.get('/update_settings?reminder_email=yes')

        self.request_fetcher.get('/admin/send_reminder_email')
        self.assertEmailNotSentTo('does_not_have_snippet@example.com')
        self.assertEmailSentTo('has_no_snippets@example.com')

    def testViewReminderMailsSettingAndSendViewEmail(self):
        self.login('does_not_have_snippet@example.com')
        self.request_fetcher.get('/update_settings?reminder_email=no')
        self.login('has_no_snippets@example.com')
        self.request_fetcher.get('/update_settings?reminder_email=yes')

        self.request_fetcher.get('/admin/send_view_email')
        self.assertEmailSentTo('has_snippet@example.com')
        self.assertEmailNotSentTo('does_not_have_snippet@example.com')
        self.assertEmailSentTo('has_many_snippets@example.com')
        self.assertEmailSentTo('has_no_snippets@example.com')

    def testEmailQuotas(self):
        """Test that we don't send more than 32 emails a minute."""
        self.total_sleep_seconds = 0
        self.sleep_seconds_this_minute = 0
        self.calls_this_minute = 0
        self.max_calls_per_minute = 0

        def count_calls_per_minute(sleep_seconds):
            self.calls_this_minute += 1
            self.sleep_seconds_this_minute += sleep_seconds
            self.total_sleep_seconds += sleep_seconds
            # Update every time through so we count the last minute too.
            self.max_calls_per_minute = max(self.max_calls_per_minute,
                                            self.calls_this_minute)
            if self.sleep_seconds_this_minute > 60:  # on to the next minute
                self.calls_this_minute = 0
                self.sleep_seconds_this_minute %= 60

        time.sleep = lambda sec: count_calls_per_minute(sec)

        # We'll do 500 users.  Rather than go through the request
        # API, we modify the db directly; it's much faster.
        users = [models.User(email='snippets%d@example.com' % i)
                 for i in xrange(500)]
        db.put(users)

        self.request_fetcher.get('/admin/send_view_email')
        # https://developers.google.com/appengine/docs/quotas#Mail
        self.assertTrue(self.max_calls_per_minute <= 32,
                        '%d <= %d' % (self.max_calls_per_minute, 32))
        # Make sure we're not too slow either: say 1/2.5 seconds on average.
        self.assertTrue(self.total_sleep_seconds <= len(users) * 2.5,
                        '%d <= %d' % (self.total_sleep_seconds,
                                      len(users) * 2.5))


class TitleCaseTestCase(unittest.TestCase):
    def testSimple(self):
        self.assertEqual('A Word to the Wise',
                         snippets._title_case('a word to the wise'))

    def testWeirdCasing(self):
        self.assertEqual('A Word to the Wise',
                         snippets._title_case('a wOrd to The WIse'))


if __name__ == '__main__':
    unittest.main()
