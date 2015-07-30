"""
Formatters are functions that convert a raw value into a human readable representation.
Formatters are assigned to a specific column to format the output.
Define here new formatters -- they take one argument and return a string.
"""
from datetime import timedelta

def memory_formatter(mem):
    """
    Takes a numeric value \p mem and returns a string using the standard prefixes K,
    M, G. The printed string has one decimal digit for GB, otherwise is integral.
    """
    if mem is None: return None
    if mem < 1000:
        return str(mem)
    if mem < 1000000:
        return str(int(mem / 1000)) + ' KB'
    if mem < 1000000000:
        return str(int(mem / 1000000)) + ' MB'
    return '%0.1f GB' % (float(mem) / 1000000000.0)

def milliseconds_formatter(time):
    """
    Formats a timedelta object by reurning the total milliseconds with three decimal
    digits, followed by the unit 'ms'.
    """
    if time is None: return None
    return '%0.3f ms' % (1000.0 * time.total_seconds())

def time_seconds_formatter(time):
    """
    Format a timedelta object according to the default timedelta.__str__ conversion,
    but tuncates the number to the seconds (no milliseconds).
    """
    if time is None: return None
    return str(timedelta(seconds=int(time.total_seconds())))

def meters_formatter(f):
    """
    Returns a float with 4 decimal digits and the unit 'm' as suffix.
    """
    if f is None: return None
    return '%0.4f m' % f
