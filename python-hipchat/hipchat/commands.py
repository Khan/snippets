import itertools
import random
import sys

if sys.version_info[0] == 2 and sys.version_info[1] < 6:
    import simplejson as json
else:
    import json

from os.path import exists
from sys import argv

import hipchat.config
import hipchat.room
import hipchat.user

class NoConfigException(Exception): pass

def init_sys_cfg():
    if exists('hipchat.cfg'):
        hipchat.config.init_cfg('hipchat.cfg')
    elif exists('~/.hipchat.cfg'):
        hipchat.config.init_cfg('~/.hipchat.cfg')
    elif exists('/etc/hipchat.cfg'):
        hipchat.config.init_cfg('/etc/hipchat.cfg')
    else:
        raise NoConfigException

class ArgsException(Exception): pass


def list_users():
    init_sys_cfg()
    print json.dumps(map(hipchat.user.User.get_json, hipchat.user.User.list()))


def add_user():
    try:
        dont_care, email, name, title, is_admin, password, timezone = argv
    except ValueError:
        raise ArgsException("%s <email> <name> <title> <is_admin> <password> <timezone>" % argv[0])
    init_sys_cfg()
    print hipchat.user.User.create(email=email,
                                   name=name,
                                   title=title,
                                   is_group_admin=is_admin,
                                   password=password,
                                   timezone=timezone)


def disable_user():
    try:
        dont_care, email = argv
    except ValueError:
        raise ArgsException("%s <email>" % argv[0])
    init_sys_cfg()
    user_id = hipchat.user.User.show(user_id=email).user_id
    print hipchat.user.User.update(user_id=user_id,
                                   password="".join([x('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890:"<\',.>;|\\+=-_~`!@#$%%^&*(){}1234567890[]') for x in itertools.repeat(random.choice, 20)])) #i'm sure there's a better way to do this, but too lazy to do research


def enable_user():
    try:
        dont_care, email, password = argv
    except ValueError:
        raise ArgsException("%s <email> <password>" % argv[0])
    init_sys_cfg()
    user_id = hipchat.user.User.show(user_id=email).user_id
    print hipchat.user.User.update(user_id=user_id,
                                   password=password)


def show_user():
    try:
        dont_care, email = argv
    except ValueError:
        raise ArgsException("%s <email>" % argv[0])
    init_sys_cfg()
    print hipchat.user.User.show(user_id=email)


def set_user_password():
    try:
        dont_care, email, password = argv
    except ValueError:
        raise ArgsException("%s <email> <password>" % argv[0])
    init_sys_cfg()
    user_id = hipchat.user.User.show(user_id=email).user_id
    print hipchat.user.User.update(user_id=user_id,
                                   password=password)


def set_user_name():
    try:
        dont_care, email, name = argv
    except ValueError:
        raise ArgsException("%s <email> <name>" % argv[0])
    init_sys_cfg()
    user_id = hipchat.user.User.show(user_id=email).user_id
    print hipchat.user.User.update(user_id=user_id,
                                   name=name)


def set_user_admin():
    try:
        dont_care, email, is_admin = argv
    except ValueError:
        raise ArgsException("%s <email> <is_admin>" % argv[0])
    init_sys_cfg()
    user_id = hipchat.user.User.show(user_id=email).user_id
    print hipchat.user.User.update(user_id=user_id,
                                   is_group_admin=is_admin)


def set_user_timezone():
    try:
        dont_care, email, timezone = argv
    except ValueError:
        raise ArgsException("%s <email> <timezone>" % argv[0])
    init_sys_cfg()
    user_id = hipchat.user.User.show(user_id=email).user_id
    print hipchat.user.User.update(user_id=user_id,
                                   timezone=timezone)


def set_user_title():
    try:
        dont_care, email, title = argv
    except ValueError:
        raise ArgsException("%s <email> <title>" % argv[0])
    init_sys_cfg()
    user_id = hipchat.user.User.show(user_id=email).user_id
    print hipchat.user.User.update(user_id=user_id,
                                   title=title)


def del_user():
    try:
        dont_care, email = argv
    except ValueError:
        raise ArgsException("%s <email>" % argv[0])
    init_sys_cfg()
    print hipchat.user.User.delete(user_id=email)
