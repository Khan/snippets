# Work under either python2.5 or python2.7
try:
    import unittest2 as unittest
except ImportError:
    import unittest
import datetime
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


_TEST_TODAY = datetime.date(2012, 2, 23)


class SnippetsTestBase(unittest.TestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_user_stub()
        self.request_fetcher = webtest.TestApp(snippets.application)
        snippets._TODAY = _TEST_TODAY

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
        # The +1 is because the 0-th element is stuff before the 1st snippet.
        # If we get an IndexError, it means there aren't that many snippets.
        try:
            return body.split('class="snippet_divider"',
                              snippet_number+2)[snippet_number+1]
        except IndexError:
            raise IndexError('Has fewer than %d snippets:\n%s'
                             % (snippet_number, body))

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
    """The most common base: someone who is logged in as user@example.com."""
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


class ShowCorrectWeekTestCase(UserTestBase):
    """Test we show the right snippets for edit/view based on day of week."""

    def testMonday(self):
        # For adding new snippets, you have until Wed to add for last week.
        snippets._TODAY = datetime.date(2012, 2, 20)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 13, 2012', response.body, 0)
        # For *viewing*'s snippets, we always show last week's snippets.
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testTuesday(self):
        snippets._TODAY = datetime.date(2012, 2, 21)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 13, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testWednesday(self):
        snippets._TODAY = datetime.date(2012, 2, 22)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 13, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testThursday(self):
        snippets._TODAY = datetime.date(2012, 2, 23)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testFriday(self):
        snippets._TODAY = datetime.date(2012, 2, 24)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testSaturday(self):
        snippets._TODAY = datetime.date(2012, 2, 25)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)

    def testSunday(self):
        snippets._TODAY = datetime.date(2012, 2, 26)
        response = self.request_fetcher.get('/')
        self.assertInSnippet('February 20, 2012', response.body, 0)
        response = self.request_fetcher.get('/weekly')
        self.assertIn('February 13, 2012', response.body)


class NosnippetGapFillingTestCase(UserTestBase):
    """Test we show correct text when folks miss a week for snippets."""

    def testNoSnippets(self):
        response = self.request_fetcher.get('/')
        self.assertNumSnippets(response.body, 1)
        self.assertInSnippet('(No snippet for this week)', response.body, 0)

        # If nobody entered a snippet, the user-db will be empty.
        response = self.request_fetcher.get('/weekly')
        self.assertNumSnippets(response.body, 0)

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
        UserTestBase.setUp(self)
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
        self.assertInSnippet('font color', response.body, 1)
        self.assertInSnippet('no see um', response.body, 1)
        # And we should see public snippets, not in gray.
        self.assertInSnippet('public@example.com', response.body, 3)
        self.assertNotInSnippet('font color', response.body, 3)
        self.assertInSnippet('see me', response.body, 3)
        
        self.login('random@some_other_domain.com')
        response = self.request_fetcher.get('/weekly?week=02-13-2012')
        self.assertNumSnippets(response.body, 4)
        self.assertInSnippet('private@some_other_domain.com', response.body, 2)
        self.assertInSnippet('foreign', response.body, 2)
        self.assertInSnippet('font color', response.body, 2)
        # Now we shouldn't see stuff from example.com
        self.assertInSnippet('private@example.com', response.body, 1)
        self.assertNotInSnippet('no see um', response.body, 1)
        # And we should also see public snippets, not in gray.
        self.assertInSnippet('public@example.com', response.body, 3)
        self.assertNotInSnippet('font color', response.body, 3)
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


class SendingEmailTestCase(UserTestBase):
    """Test we correctly send cron emails."""

    def setUp(self):
        UserTestBase.setUp(self)
        self.testbed.init_mail_stub()
        self.mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)

        # For our mail tests, we set up a db with a few users, some of
        # whom have snippets for this week ('this week' being 13 Feb
        # 2012), some of whom don't.
        self.login('has_snippet@example.com')
        self.request_fetcher.get('/update_snippet?week=02-13-2012&snippet=s1')

        self.login('has_many_snippets@example.com')
        self.request_fetcher.get('/update_snippet?week=02-06-2012&snippet=s2')
        self.request_fetcher.get('/update_snippet?week=02-13-2012&snippet=s3')

        self.login('does_not_have_snippet@example.com')
        self.request_fetcher.get('/update_snippet?week=02-06-2012&snippet=s4')

        self.login('has_no_snippets@example.com')
        self.request_fetcher.get('/settings')

        self.login('user@example.com')        # back to the normal user
        
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
