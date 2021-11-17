"""
"""

import os

REGISTERED_VARS = [
    ("WSGI_DRAGON_GATEWAY_TIMEOUT", "10",
     "Gateway Timeout is the time waited to handle a request before 504 Gateway Timeout is returned." +
     " This value will be ignored if X-Timeout header is sent in the request."),
]

REGISTERED_VARS.sort(key=lambda x: x[0])


class EnvironMeta(type):
    def __new__(meta, name, bases, dct):

        env_vars = {}
        for (k, d, _) in REGISTERED_VARS:
            env_vars[k] = os.environ.get(k, d)

        cls_dct = {
            **dct,
            "__ENV_VARS": env_vars,
            "__len__": env_vars.__len__,
            "__iter__": env_vars.__iter__,
            "__contains__": env_vars.__contains__,
            "__getitem__": env_vars.__getitem__,
            "keys": env_vars.keys,
            "items": env_vars.items,
            "values": env_vars.values,
            "get": env_vars.get,
            "__eq__": env_vars.__eq__,
            "__ne__": env_vars.__ne__,
        }

        return super().__new__(meta, name, bases, cls_dct)


class Environ(metaclass=EnvironMeta):

    # Copy the registered vars from WSGI Dragon
    __REGISTERED_VARS = REGISTERED_VARS[:]

    @classmethod
    def register(cls, name, default_value, doc):
        cls.__REGISTERED_VARS.append((name, default_value, doc))

        # Save it
        cls.__dict__['__ENV_VARS'][name] = os.environ.get(name, default_value)

    def description(self, name):
        for (k, _, d) in self.__class__.__REGISTERED_VARS:
            if k == name:
                return d

        raise KeyError(f"unrecognised name {name}")


environ = Environ()
