Snippet Server
==============

This server supports writing and reading weekly snippets -- status
updates -- for a group of people.

Every company I've worked at, one of the first things I did was write
a small server to manage snippets.  (The one at Google eventually
became a big server.)  Now I'm open sourcing one so I won't have to
write it again!

While there are [many](https://weekdone.com/)
[snippet](https://www.workingon.co/)
[systems](https://www.teamsnippets.com/) out there, this one is
optimized for simplicity (also, free-ness).  For instance, it prefers
single webpages with lots of info over paging, queries, or fancy
javascript.  This makes it easy to learn and easy to program with.


What are weekly snippets?
-------------------------

A weekly snippet is an (ideally) brief description of what you did the
last week.  To give an idea of 'brief': the snippet-entry textbox is
sized for 4 bullet-point entries, each 80 characters or less.

Your snippets are visible to everyone else on your email domain.  (So
my snippets are visible to everyone who logs in to KA snippet server
with a `@khanacademy.org` email address.)  Depending on your
configuration options, they may also be visible to everyone else in
the world.


Why have snippets?
------------------

Different people might have different purposes for weekly snippets:

* Instead of a weekly standup or other meeting where everyone shares
  what they've done in the last week, they can just read (and write)
  snippets.
* Managers can read snippets of their direct reports to make better
  use of 1-on-1 meetings.
* You can look over your own snippets when writing a self-evaluation
  or applying for a promotion, or when you have any other need to remind
  yourself what you've worked on.

I've found this last reason is particularly compelling.  I also use
snippets as a simple "time and motion" study: when I have too many
things to put into snippets one week, I know I'm being spread too
thin!

Another benefit of snippets is serendipidous helping: by reading
someone's snippet, you may discover a task or problem they're working
on that you can help with, that otherwise you would never have known
about.


What are snippets not good for?
-------------------------------

Some people go into a snippet system with unrealistic expectations and
are disappointed.

* Snippets do not work well for large groups, say **over 100
  people**.  If you have 1000 people using your snippet server, it is
  neither practical nor useful to read through everyone's snippets
  every week.

* Snippets are, by design, a low level tool: they show you trees but
  not the forest.  The snippet system does not support "rolling up"
  groups of snippets or having team-based snippets (though certain
  individuals could certainly choose to have their own snippets refer
  to a team's progress).

* Snippets do not provide context.  If you don't already know what
  someone is working on, their snippet may well be more confusing
  than enlightening.

At Khan Academy, the entire company uses one snippet server.  The
snippets are divided into various categories, some functional, some
project-based.  I like to skim over the snippets for people in
unrelated categories such as "facilities" or "recruiting."  I read
more closely the snippets in projects I'm interested in but not
working on, such as "mobile."  And I read most closely the snippets of
people in my own project or closely related projects.


How do you use the snippet-server?
==================================

After setting up your settings, to control things like how public your
snippets are and whether you want to use plain text or
[markdown](https://daringfireball.net/projects/markdown/), there are
only two web pages: the one where you write your snippets, and the one
where you read everyone's snippets for a week.

The administrator can set up the system to send you reminder emails to
write snippets, or to email when snippets are ready for a week.  (The
snippet server can also use chat systems for this.)


System requirements
-------------------

The snippet server is built on top of [Google
AppEngine](https://cloud.google.com/appengine/docs), and uses Google
services for authentication.  To use it, you need to clone the
[snippet github project](https://github.com/Khan/snippets) and then
upload it to your own appengine instance.  (It uses few resources, so
Google's "free tier" would work fine.)

The people using your snippet server must log in using Google (aka
Gmail) accounts.  The snippet server works particularly well with
companies that use [Google Apps for Work](https://apps.google.com).


Access control
--------------

When a snippet server is first set up, the administrator restricts it
to specific domains.  (The Khan Academy server, for instance, is
restricted to `@khanacademy.org`.)  If you want to create a snippet on
the server, you must log in via an email address from one of those
domains.

You can set your snippet to be either "public" or "private".  "Public"
snippets are visible to everyone who has access to your snippet
server.  "Private" snippets are visible only to people on the same
domain as you.  So if you logged in as `jane@example.com`, only other
users at `example.com` would be able to see your Snippet.


Email and chat
--------------

The snippet server integrates with email, HipChat, and Slack.

It can send individual emails to people who have not written a snippet
for this week, reminding them to do so.  (Users can turn this feature
off in their preferences.)  It can also send an email to all
registered users, at 5pm on Monday, to say snippets are ready.

It can also send reminders and ready messages via chat.  (In this
case, the reminder isn't individualized.)
