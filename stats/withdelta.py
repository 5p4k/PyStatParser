class withdelta(object):
    """
    Wraps any object into the `value` property, and adds a `delta` floating point property
    that can be used to store extra information, such as percentage of improvement over a
    over a different values.

    All the attributes are forwarded to `value`, except for `value` and `delta`. This means
    that you can call any weird method on withdelta, and this will reflect the implementation
    of the current object stored in `value`.

    Use val_of to quickly unwrap any object from its withdelta wrapper.
    """
    value = None
    delta = None
    def __getattr__(self, name):
        if name in ['value', 'delta']:
            return super(withdelta, self).__getattr__(name)
        else:
            return getattr(self.value, name)
    def __setattr__(self, name, value):
        if name in ['value', 'delta']:
            super(withdelta, self).__setattr__(name, value)
        else:
            setattr(self.value, name, value)
    def __repr__(self):
        return 'withdelta(' + str(self.value) + ', ' + str(self.delta) + ')'
    def __init__(self, obj, delta = float('NaN')):
        self.value = obj
        self.delta = delta

def val_of(obj):
    """
    Returns `obj.value` if obj is a withdelta instance, otherwise just obj.
    """
    return obj.value if isinstance(obj, withdelta) else obj

