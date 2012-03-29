#!/usr/bin/env python                                                                                                                                           

from setuptools import setup, find_packages

setup(
    name = "hipchat",
    version = "0.0.1",
    packages = find_packages(),

    author = "Yaakov M Nemoy",
    author_email = "loup@hexago.nl",
    description = "Pythonic interface on top of HipChat RPC",
    license = "WTFPL",

    entry_points = {
        'console_scripts': [
            'hipchat-add-user = hipchat.commands:add_user',
            'hipchat-disable-user = hipchat.commands:disable_user',
            'hipchat-enable-user = hipchat.commands:enable_user',
            'hipchat-list-users = hipchat.commands:list_users',
            'hipchat-show-user = hipchat.commands:show_user',
            'hipchat-set-user-password = hipchat.commands:set_user_password',
            'hipchat-set-user-name = hipchat.commands:set_user_name',
            'hipchat-set-user-admin = hipchat.commands:set_user_admin',
            'hipchat-set-user-timezone = hipchat.commands:set_user_timezone',
            'hipchat-set-user-title = hipchat.commands:set_user_title',
            'hipchat-del-user = hipchat.commands:del_user',
            ]
        },
    )
