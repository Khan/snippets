# Work under either python2.5 or python2.7
try:
    import unittest2 as unittest
except ImportError:
    import unittest
import os
import snippets
import webtest   # may need to do 'pip install webtest'

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import testbed


"""Tests for the snippets server.

This tests the functionality found at weekly-snippets.appspot.com.

c.f. http://code.google.com/appengine/docs/python/tools/localunittesting.html
"""

__author__ = 'Craig Silverstein <csilvers@khanacademy.org>'


class SnippetsTestBase(unittest.TestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_user_stub()
        self.request_fetcher = webtest.TestApp(snippets.application)

    def tearDown(self):
        self.testbed.deactivate()

    def login(self, email):
        self.testbed.setup_env(user_email=email, overwrite=True)
        self.testbed.setup_env(user_id=email, overwrite=True)
        self.testbed.setup_env(user_is_admin='0', overwrite=True)

    def set_is_admin(self):
        self.testbed.setup_env(user_is_admin='1', overwrite=True)

    def assertNumSnippets(self, body, expected_count):
        """Asserts the page 'body' has exactly expected_count snippets in it."""
        # We annotate the element at the beginning of each snippet with
        # class="snippet_divider".
        self.assertEqual(expected_count, body.count('class="snippet_divider"'),
                         body)

    def _ith_snippet(self, body, snippet_number):
        """For user- and weekly-pages, return the i-th snippet, 0-indexed."""
        # The +1 is because the 0-th element is stuff before the 1st snippet
        return body.split('class="snippet_divider"',
                          snippet_number+2)[snippet_number+1]

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
        """For snippet-page 'body', assert 'text' is not in the i-th snippet."""
        self.assertNotIn(text, self._ith_snippet(body, snippet_number))


class UserTestBase(SnippetsTestBase):
    """The common base: someone who is logged in as user@example.com."""
    def setUp(self):
        SnippetsTestBase.setUp(self)
        self.login('user@example.com')


class LoginRequiredTestCase(SnippetsTestBase):
    def testLoginRequiredForUserView(self):
        url = '/'
        response = self.request_fetcher.get(url)
        self.assertIn('must be logged in', response.body)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assertNotIn('must be logged in', response.body)

    def testLoginRequiredForWeeklyView(self):
        url = '/weekly'
        response = self.request_fetcher.get(url)
        self.assertIn('must be logged in', response.body)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assertNotIn('must be logged in', response.body)

    def testLoginRequiredForSettingsView(self):
        url = '/settings'
        response = self.request_fetcher.get(url)
        self.assertIn('must be logged in', response.body)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assertNotIn('must be logged in', response.body)

    def testLoginRequiredToUpdateSnippet(self):
        url = '/update_snippet?week=02-20-2012&snippet=my+snippet'
        response = self.request_fetcher.get(url)
        self.assertIn('must be logged in', response.body)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assertNotIn('must be logged in', response.body)
        
    def testLoginRequiredToUpdateSettings(self):
        url = '/update_settings'
        response = self.request_fetcher.get(url)
        self.assertIn('must be logged in', response.body)

        self.login('user@example.com')
        response = self.request_fetcher.get(url)
        self.assertNotIn('must be logged in', response.body)


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
