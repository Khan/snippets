import datetime

from models import Snippet
from models import User


# Functions for retrieving a user
def get_user(email):
    """Return the user object with the given email, or None if not found."""
    q = User.all()
    q.filter('email = ', email)
    return q.get()


def get_user_or_die(email):
    user = get_user(email)
    if not user:
        raise ValueError('User "%s" not found' % email)
    return user


def snippets_for_user(user_email):
    """Return all snippets for a given user, oldest snippet first."""
    snippets_q = Snippet.all()
    snippets_q.filter('email = ', user_email)
    snippets_q.order('week')            # this puts oldest snippet first
    return snippets_q.fetch(1000)       # good for many years...


def most_recent_snippet_for_user(user_email):
    """Return the most recent snippet for a given user, or None."""
    snippets_q = Snippet.all()
    snippets_q.filter('email = ', user_email)
    snippets_q.order('-week')            # this puts newest snippet first
    return snippets_q.get()


# Functions around filling in snippets
def newsnippet_monday(today):
    """Return a datetime.date object: the monday for new snippets.

    We just return the monday for this week.  Saturday and Sunday
    map to the previous monday.

    Note that this means when you look at snippets for monday, you're
    offered to enter snippets for the week that has just started, even
    though not much has happened yet!  This is for people who like to
    enter snippets as they go along.  For those people who wait until
    monday to fill in the previous week's snippets, they can still do
    so; the second snippet box will be marked 'DUE TODAY'.

    Arguments:
       today: the current day as a datetime.datetime object, used to
          calculate the best monday.

    Returns:
       The Monday that we are accepting new snippets for, by default,
       as a datetime.date (not datetime.datetime) object.
    """
    today_weekday = today.weekday()   # monday == 0, sunday == 6
    end_monday = today - datetime.timedelta(today_weekday)
    return end_monday.date()


def existingsnippet_monday(today):
    """Return a datetime.date object: the monday for existing snippets.

    The rule is that we show the snippets for the previous week.  We
    declare a week starts on Monday...well, actually, Sunday at 11pm.
    The reason for this is that (for quota reasons) we sent out a
    reminder email Sunday at 11:50pm rather than Monday morning, and
    we want that to count as 'Monday' anyway...

    Arguments:
       today: the current day as a datetime.datetime object, used to
          calculate the best monday.

    Returns:
       The Monday that we are accepting new snippets for, by default,
       as a datetime.date (not datetime.datetime) object.
    """
    today_weekday = today.weekday()   # monday == 0, sunday == 6
    if today_weekday == 6 and today.hour >= 23:
        end_monday = today - datetime.timedelta(today_weekday)
    else:
        end_monday = today - datetime.timedelta(today_weekday + 7)
    return end_monday.date()


def fill_in_missing_snippets(existing_snippets, user, user_email, today):
    """Make sure that the snippets array has a Snippet entry for every week.

    The db may have holes in it -- weeks where the user didn't write a
    snippet.  Augment the given snippets array so that it has no holes,
    by adding in default snippet entries if necessary.  Note it does
    not add these entries to the db, it just adds them to the array.

    Arguments:
       existing_snippets: a list of Snippet objects for a given user.
         The first snippet in the list is assumed to be the oldest
         snippet from that user (at least, it's where we start filling
         from).
       user: a User object for the person writing this snippet.
       user_email: the email of the person whose snippets it is.
       today: a datetime.datetime object representing the current day.
         We fill up to then.  If today is wed or before, then we
         fill up to the previous week.  If it's thurs or after, we
         fill up to the current week.

    Returns:
      A new list of Snippet objects, without any holes.
    """
    end_monday = newsnippet_monday(today)
    if not existing_snippets:         # no snippets at all?  Just do this week
        return [Snippet(email=user_email, week=end_monday,
                        private=user.private_snippets,
                        is_markdown=user.uses_markdown)]

    # Add a sentinel, one week past the last week we actually want.
    # We'll remove it at the end.
    existing_snippets.append(Snippet(email=user_email,
                                     week=end_monday + datetime.timedelta(7)))

    all_snippets = [existing_snippets[0]]   # start with the oldest snippet
    for snippet in existing_snippets[1:]:
        while snippet.week - all_snippets[-1].week > datetime.timedelta(7):
            missing_week = all_snippets[-1].week + datetime.timedelta(7)
            all_snippets.append(Snippet(email=user_email, week=missing_week,
                                        private=user.private_snippets,
                                        is_markdown=user.uses_markdown))
        all_snippets.append(snippet)

    # Get rid of the sentinel we added above.
    del all_snippets[-1]

    return all_snippets
