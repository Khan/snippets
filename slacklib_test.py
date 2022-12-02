#!/usr/bin/env python
# -*- coding: utf-8 -*-


import datetime
import textwrap
import unittest

from google.cloud import ndb
from google.appengine.ext import testbed

import models
import slacklib


class SlashCommandTest(unittest.TestCase):

    def _mock_data(self):
        # The fictional day for these tests Wednesday, July 29, 2015
        slacklib._TODAY_FN = lambda: datetime.datetime(2015, 7, 29)

        # Stuart created his account, but has never once filled out a snippet
        models.User(email='stuart@khanacademy.org').put()

        # Fleetwood has two recent snippets, and always uses markdown lists,
        # but sometimes uses different list indicators or indention.
        models.User(email='fleetwood@khanacademy.org').put()
        models.Snippet(
            email='fleetwood@khanacademy.org',
            week=datetime.date(2015, 7, 27),
            text=textwrap.dedent("""
            *  went for a walk
            *  sniffed some things
            *  hoping to sniff more things! #yolo
            """)
        ).put()
        models.Snippet(
            email='fleetwood@khanacademy.org',
            week=datetime.date(2015, 7, 20),
            text=textwrap.dedent("""
            - lots of walks this week
            - not enough sniffing, hope to remedy next week!
            """)
        ).put()

        # Toby has filled out two snippets, but missed a week in-between while
        # on vacation. When he got back from vacation he was still jetlagged so
        # he wrote a longform paragraph instead of a list.
        models.User(email='toby@khanacademy.org').put()
        models.Snippet(
            email='toby@khanacademy.org',
            week=datetime.date(2015, 7, 13),
            text=textwrap.dedent("""
            - going on vacation next week, so excited!


            """)
        ).put()
        models.Snippet(
            email='toby@khanacademy.org',
            week=datetime.date(2015, 7, 27),
            text=textwrap.dedent("""
            I JUST GOT BACK FROM VACATION IT WAS TOTALLY AWESOME AND I SNIFFED
            ALL SORTS OF THINGS.  I GUESS I NEED TO WRITE SOMETHING HERE, HUH?

            OK THEN:
            - I had fun.

            LUNCHTIME SUCKERS!
            """)
        ).put()

        # Fozzie tried hard to create an entry manually in the previous week,
        # but didn't understand markdown list syntax and got discouraged (so
        # has no entry this week, and a malformed one last week).
        models.User(email='fozzie@khanacademy.org').put()
        models.Snippet(
            email='fozzie@khanacademy.org',
            week=datetime.date(2015, 7, 20),
            text=textwrap.dedent("""
            -is this how I list?
            -why is it not formatting??!?
            """)
        ).put()

    def _most_recent_snippet(self, user_email):
        snippets_q = models.Snippet.query(
            models.Snippet.email == user_email
        ).order('-week')  # newest snippet first
        return snippets_q.fetch(1)[0]

    def setUp(self):
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_memcache_stub()
        self._mock_data()

    def tearDown(self):
        self.testbed.deactivate()

    def testDumpCommand_empty(self):
        # user without a recent snippet should just see null text
        response = slacklib.command_dump('stuart@khanacademy.org')
        self.assertIn('No snippet yet for this week', response)

    def testDumpCommand_formatting(self):
        # user with a snippet should just get it back unformatted
        response = slacklib.command_dump('fleetwood@khanacademy.org')
        self.assertIn('#yolo', response)

    def testDumpCommand_noAccount(self):
        # user without an account should get a helpful error message
        response = slacklib.command_dump('bob@bob.com')
        self.assertIn("You don't appear to have a snippets account", response)
        self.assertIn("Slack email address: bob@bob.com", response)

    def testListCommand_empty(self):
        # user without a recent snippet should get a helpful message
        response = slacklib.command_list('stuart@khanacademy.org')
        self.assertIn(
            "You don't have any snippets for this week yet!", response
        )

    def testListCommand_formatting(self):
        # user with snippet should get back a formatted, numbered list
        response = slacklib.command_list('fleetwood@khanacademy.org')
        self.assertIn('> :pushpin: *[0]* went for a walk', response)
        self.assertIn(
            '> :pushpin: *[2]* hoping to sniff more things! #yolo',
            response
        )

    def testListCommand_noAccount(self):
        # user without an account should get a helpful error message
        response = slacklib.command_list('bob@bob.com')
        self.assertIn("You don't appear to have a snippets account", response)

    def testLastCommand_empty(self):
        # user without a snippet last week should get a helpful message
        expect = "You didn't have any snippets last week!"
        # stuart never fills out
        self.assertIn(expect, slacklib.command_last('stuart@khanacademy.org'))
        # toby skipped last week
        self.assertIn(expect, slacklib.command_last('toby@khanacademy.org'))

    def testLastCommand_formatting(self):
        # user with snippet should get back a formatted, numbered list
        response = slacklib.command_last('fleetwood@khanacademy.org')
        self.assertIn('> :pushpin: *[0]* lots of walks this week', response)

    def testLastCommand_noAccount(self):
        # user without an account should get a helpful error message
        response = slacklib.command_last('bob@bob.com')
        self.assertIn("You don't appear to have a snippets account", response)

    def testBadMarkdown_listCommand(self):
        toby_recent = slacklib.command_list('toby@khanacademy.org')
        self.assertIn("not in a format I understand", toby_recent)

    def testBadMarkdown_lastCommand(self):
        fozzie_last = slacklib.command_last('fozzie@khanacademy.org')
        self.assertIn("not in a format I understand", fozzie_last)

    def testAddCommand_blank(self):
        # blank slate should be easy...
        r = slacklib.command_add('stuart@khanacademy.org', 'went to the park')
        t = self._most_recent_snippet('stuart@khanacademy.org')
        self.assertIn("Added *went to the park* to your weekly snippets", r)
        self.assertEqual('- went to the park', t.text)
        self.assertEqual(True, t.is_markdown)

    def testAddCommand_existing(self):
        # on this one, the user markdown formatting gets altered/standardized
        slacklib.command_add('fleetwood@khanacademy.org', 'went to the park')
        t = self._most_recent_snippet('fleetwood@khanacademy.org')
        expected = textwrap.dedent("""
            - went for a walk
            - sniffed some things
            - hoping to sniff more things! #yolo
            - went to the park
        """).strip()
        self.assertEqual(expected, t.text)
        self.assertEqual(True, t.is_markdown)

    def testAddCommand_existingIsMalformed(self):
        # we should be told we cannot to add to a snippet that is malformed!
        toby_email = 'toby@khanacademy.org'
        r = slacklib.command_add(toby_email, 'went to the park')
        self.assertIn("Your snippets are not in a format I understand", r)
        # ...and the existing snippets should not have been touched
        t = self._most_recent_snippet(toby_email)
        self.assertNotIn("went to the park", t.text)
        self.assertIn("LUNCHTIME SUCKERS!", t.text)
        self.assertEqual(False, t.is_markdown)

    def testAddCommand_noArgs(self):
        # we need to handle when they try to add nothing!
        r = slacklib.command_add('stuart@khanacademy.org', '')
        self.assertIn("*what* do you want me to add exactly?", r)

    def testAddCommand_noAccount(self):
        # dont crash horribly if user doesnt exist
        r = slacklib.command_add('bob@bob.com', 'how is account formed?')
        self.assertIn("You don't appear to have a snippets account", r)

    def testAddCommand_markupUsernames(self):
        # usernames should be marked up properly so they get syntax highlighted
        r = slacklib.command_add('stuart@khanacademy.org', 'ate w/ @toby, yay')
        t = self._most_recent_snippet('stuart@khanacademy.org')
        self.assertIn("ate w/ <@toby>, yay", r)
        self.assertIn("- ate w/ <@toby>, yay", t.text)

    def testAddCommand_unicode(self):
        r = slacklib.command_add('stuart@khanacademy.org', 'i “like” food')
        t = self._most_recent_snippet('stuart@khanacademy.org')
        self.assertIn('i “like” food', r)
        self.assertIn('i “like” food', t.text)

    def testDelCommand_noArgs(self):
        # we need to handle when they try to add nothing!
        r = slacklib.command_del('stuart@khanacademy.org', [])
        self.assertIn("*what* do you want me to delete exactly?", r)

    def testDelCommand_noAccount(self):
        # dont crash horribly if user doesnt exist
        r = slacklib.command_del('bob@bob.com', ['1'])
        self.assertIn("You don't appear to have a snippets account", r)

    def testDelCommand_normalCase(self):
        r = slacklib.command_del('fleetwood@khanacademy.org', ['1'])
        t = self._most_recent_snippet('fleetwood@khanacademy.org')
        self.assertIn(
            "Removed *sniffed some things* from your weekly snippets", r)
        expected = textwrap.dedent("""
            - went for a walk
            - hoping to sniff more things! #yolo
        """).strip()
        self.assertEqual(expected, t.text)
        self.assertEqual(True, t.is_markdown)

    def testDelCommand_nonexistentIndex(self):
        r1 = slacklib.command_del('stuart@khanacademy.org', ['0'])
        r2 = slacklib.command_del('fleetwood@khanacademy.org', ['4'])
        expected = "You don't have anything at that index"
        self.assertIn(expected, r1)
        self.assertIn(expected, r2)

    def testDelCommand_indexNaN(self):
        r = slacklib.command_del('bob@bob.com', ['one'])
        self.assertIn("*what* do you want me to delete exactly?", r)

    def testDelCommand_existingIsMalformed(self):
        # we should be told we cannot to add to a snippet that is malformed!
        r = slacklib.command_del('toby@khanacademy.org', ['0'])
        self.assertIn("Your snippets are not in a format I understand", r)
        # ...and the existing snippets should not have been touched
        t = self._most_recent_snippet('toby@khanacademy.org')
        self.assertIn("I had fun", t.text)
        self.assertEqual(False, t.is_markdown)

if __name__ == '__main__':
    unittest.main()
