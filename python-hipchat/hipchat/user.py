from hipchat.connection import partial, call_hipchat, HipChatObject

class UserDeleteStatus(HipChatObject):
    sort = 'delete'
    def __init__(self, jsono):
        self.jsono = jsono
        self.deleted = jsono.get('deleted')


class User(HipChatObject):
    sort = 'user'


User.create = classmethod(partial(call_hipchat, User, url="https://api.hipchat.com/v1/users/create", data=True))
User.delete = \
    classmethod(partial(call_hipchat, 
                        ReturnType=UserDeleteStatus, 
                        url="https://api.hipchat.com/v1/users/delete", 
                        data=True))
User.list = \
    classmethod(partial(call_hipchat, 
                        ReturnType=lambda x: map(User, map(lambda y: {'user': y}, x['users'])), 
                        url="https://api.hipchat.com/v1/users/list", 
                        data=False))
User.show = classmethod(partial(call_hipchat, User, url="https://api.hipchat.com/v1/users/show", data=False))
User.update = classmethod(partial(call_hipchat, User, url="https://api.hipchat.com/v1/users/update", data=True))
