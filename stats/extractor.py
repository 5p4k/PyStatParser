"""
Main module for parsing log files. Log files are parsed sequentially, line by line.
Each line is matched against each extractor, which is a (stateful) class that can
extract a meaningful value from a string line.
"""
import re
import os.path
from withdelta import *
from datetime import timedelta

class ExtractorBase(object):
    """
    The base class that pulls data out of the log files. Subclasses should implement
    `extract_value_from_line`, and optionally `postprocess`.
    When more than one match is found, to resolve the ambiguity one of the following
    policies is applied:
        - POLICY_KEEP_LAST: the current value is replaced with the new value.
        - POLICY_KEEP_FIRST: the new value is discarded.
        - POLICY_SUM: the new value is added to the previous (thus cumulating all the
          matches). The operator `+=` is invoked on the value returned by
          `extract_value_from_line`.
        - POLICY_APPEND: all the extracted values are inserted into a list. The
          `value` property is thus a list.

    If no match is found, `value` defaults to None.
    """
    POLICY_KEEP_LAST = 'POLICY_KEEP_LAST'
    POLICY_KEEP_FIRST = 'POLICY_KEEP_FIRST'
    POLICY_SUM = 'POLICY_SUM'
    POLICY_APPEND = 'POLICY_APPEND'

    value = None
    num_of_matches = None
    policy = None

    def extract_value_from_line(self, line):
        """
        Scan `line` and return a parsed object if a match is found, None otherwise.
        """
        return None

    def postprocess(self):
        """
        Called when the current file has been scanned.
        """
        pass

    def process_line(self, line):
        """
        Not to be overridden. Calls `extract_value_from_line` and updates `value`
        according to the value of `policy`.
        """
        candidate = self.extract_value_from_line(line)
        if candidate is not None:
            self.num_of_matches += 1
            if self.value is None:
                self.value = candidate if self.policy != ExtractorBase.POLICY_APPEND else [candidate]
            elif self.policy == ExtractorBase.POLICY_KEEP_FIRST:
                pass
            elif self.policy == ExtractorBase.POLICY_KEEP_LAST:
                self.value = candidate
            elif self.policy == ExtractorBase.POLICY_SUM:
                self.value += candidate
            elif self.policy == ExtractorBase.POLICY_APPEND:
                self.value += [candidate]
        else:
            return None

    def __init__(self, policy='POLICY_KEEP_LAST'):
        super(ExtractorBase, self).__init__()
        self.num_of_matches = 0
        self.policy = policy
        self.value = None

class RegexExtractor(ExtractorBase):
    """
    Extracts a string value from a line matched by a regular expression. The value
    returned is the value of the named group 'result' inside the regular expression.

    Example:
        `RegexExtractor('^hello\\s+(?P<result>\\w+)')`
        This extractor would match the next non-empty word following a 'hello' string
        at the beginning of the line.
    """
    # must have a group named 'result'
    regex = None

    def extract_value_from_line(self, line):
        match = self.regex.match(line)
        if match is not None:
            return match.groupdict()['result']

    def __init__(self, rgx_source, policy=ExtractorBase.POLICY_KEEP_LAST):
        super(RegexExtractor, self).__init__(policy=policy)
        self.regex = re.compile(rgx_source)

class ValueConverterExtractorBase(ExtractorBase):
    """
    Wrapper for another extractor: the value returned by that extractor
    is then fed into the `convert_raw_value` function, which has to be implemented
    by the subclasses. This can be used to perform string casts towards other types.
    """
    def convert_raw_value(self, raw_value):
        return raw_value

    def extract_value_from_line(self, line):
        candidate = self._other_extractor.extract_value_from_line(line)
        if candidate is not None:
            return self.convert_raw_value(candidate)
        else:
            return None

    def __init__(self, other_extractor, policy=ExtractorBase.POLICY_KEEP_LAST):
        super(ValueConverterExtractorBase, self).__init__(policy=policy)
        assert(isinstance(other_extractor, ExtractorBase))
        self._other_extractor = other_extractor

class IntConverterExtractor(ValueConverterExtractorBase):
    """
    Converts the matched value into int.
    """
    def convert_raw_value(self, raw_value):
        try:
            return int(raw_value)
        except:
            return None

class FloatConverterExtractor(ValueConverterExtractorBase):
    """
    Converts the matched value into float.
    """
    def convert_raw_value(self, raw_value):
        try:
            return float(raw_value)
        except:
            return None

class TimeConverterExtractor(ValueConverterExtractorBase):
    """
    Converts the matched value in the format `[[[d:]h:]m:]s[.ms]` into a timedelta object.
    """
    def convert_raw_value(self, raw_value):
        pieces = raw_value.split(':')
        if len(pieces) > 4:
            return None
        try:
            pieces = [float(piece) for piece in pieces]
        except:
            return None
        if len(pieces) < 4:
            pieces = [0.0] * (4 - len(pieces)) + pieces
        return timedelta(days=pieces[0], hours=pieces[1], minutes=pieces[2], seconds=pieces[3])

class MemoryConverterExtractor(ValueConverterExtractorBase):
    """
    Parses the suffixes 'K' 'M' 'G' (optionally followed by a 'b') and returns an integer
    with the correct size in bytes.
    """
    def convert_raw_value(self, raw_value):
        raw_value = raw_value.lower()
        factor = 1.0
        if raw_value[-1] == 'b':
            raw_value = raw_value[:-1]
        if raw_value[-1] in 'kmg':
            if raw_value[-1] == 'k':
                factor = 1000.0
            elif raw_value[-1] == 'm':
                factor = 1000000.0
            else:
                factor = 1000000000.0
            raw_value = raw_value[:-1]
        return int(float(raw_value) * factor)

class StatsExtractorBase(object):
    """
    Main object that performs the parsing of a log files. It matches each line against each
    extactor stored in the `extrators` dictionary. The keys of the dict are going to be the
    headers of the final table.

    Subclasses must implement the classmethod `get_all_extractors` that defines the extractors
    to be used, and `get_all_extracted_attributes` that returns a list of keys that represent
    the attributes that are going to be actually returned by the `as_dict` method.

    Subclasses can optionally implement also the `postprocess_scan` method.

    It is forbidden to use as key in the dictionary 'extractors' and 'extracted_attributes'.

    Dynamic attributes
    ------------------
    You can as well define attributes that are not associated to an extractors.
    All the key-extractor pairs in the `extractors` property define an attribute.
    You can return in `get_all_extracted_attributes` also keys that are not present in `extractors`:
    in this case, for a key (e.g.) 'missing_attr', you need to implement a corresponding
    `get_missing_attr` method that returns the dynamically computed value for the attribute
    'missing_attr'.

    To make access to attributes easier the following mapping is used: when `self.any_attribute` is
    looked up, if there is a 'any_attribute' extractor in `extractors`, `self.any_attribute` will
    return `self.extractors['any_attribute'].value`. If 'any_attribute' is not in `extractors`, but
    it is in `extracted_attributes`, `self.any_attribute` will internally call the method
    `self.get_any_attribute()` and returns its value.

    Data format
    -----------
    `as_dict` will return a dictionary. `scan_multiple_runs` will return a list of dictionaries.
    `group_multiple_runs` will take a list of dictionary, and return a dictionary of lists. A dictionary
    of lists is called throughout the code 'grouped runs', therefore you must call `group_multiple_runs`
    before feeding the data to `add_deltas_to_grouped_runs`, `compute_footer_from_grouped_runs`.
    """

    extractors = {}
    extracted_attributes = []

    @classmethod
    def get_all_extractors(cls):
        """
        Virtual method. Returns a dictionary with key-extractor pairs.
        """
        return {}

    @classmethod
    def get_all_extracted_attributes(cls):
        """
        Virtual method. Returns a list of keys extacted by this StatsExtractor object, that have to be
        returned by `as_dict`.
        """
        return []

    def postprocess_scan(self):
        """
        Optional postprocessing action. This is called *after* the `postprocess` method of the extractors
        has been called.
        """
        pass

    def __getattr__(self, name):
        if name in ['extractors', 'extracted_attributes']:
            raise AttributeError('Someone is messing up with __getattr__ or deleted the extracted_attributes/extractors variable...')
        elif name in self.extractors:
            return self.extractors[name].value
        elif name in self.extracted_attributes:
            if hasattr(self, 'get_' + name):
                method = getattr(self, 'get_' + name)
                if hasattr(method, '__call__'):
                    return method()
        raise AttributeError('Attribute %s is missing.' % name)

    @classmethod
    def get_delta_percent(cls, val1, val2):
        """
        Computes `(val2 - val1) / val1` for different types of data, in float.
        If the types are mismatched, None is returned. INF and NAN are valid outputs.

        Currently supports int, float, timedelta, str, unicode.
        For str and unicode the returned value is undefined.
        """
        if val1 is None and val2 is None:
            return None

        if type(val1) is not type(val2):
            return None

        if type(val1) is timedelta:
            is_valid = lambda val : val.total_seconds() >= 0.0
            to_float = lambda val : val.total_seconds()
        elif type(val1) is int:
            is_valid = lambda val : val >= 0
            to_float = lambda val : float(val)
        elif type(val1) is str or type(val1) is unicode:
            is_valid = lambda val : True
            to_float = lambda val : 0.0
        elif type(val1) is float:
            is_valid = lambda val : val == val
            to_float = lambda val : val
        else:
            is_valid = lambda val : False
            to_float = lambda val : 0.0

        if is_valid(val1) and is_valid(val2):
            if val1 == val2:
                return 0.0
            elif abs(to_float(val1)) == 0.0:
                return float('inf') if to_float(val2) > 0.0 else float('-inf')
            else:
                return (to_float(val2) - to_float(val1)) / to_float(val1)
        else:
            return float('NaN')

    def as_dict(self):
        """
        Returns a key-value pair with `extracted_attributes` as keys.
        """
        retval = {}
        for k in self.extracted_attributes:
            retval[k] = getattr(self, k)
        return retval

    def scan(self):
        """
        Parses the file line by line and calls `postprocess` on the extractors, followed by `postprocess_scan`.
        """
        for line in self._file_handle:
            for k in self.extractors:
                self.extractors[k].process_line(line)
        for k in self.extractors:
            self.extractors[k].postprocess()
        self.postprocess_scan()

    @classmethod
    def scan_multiple_runs(cls, files):
        """
        Scans each file and returns a list of StatsExtractorBase instances.
        If the file does not exists, a None placeholder is placed in the list instead.
        """
        run_list = []
        for filename in files:
            if os.path.isfile(filename):
                print('    Parsing %s...' % filename)
                with open(filename, 'r') as fh:
                    extractor = cls(fh)
                    extractor.scan()
                    run_list.append(extractor)
            else:
                run_list.append(None)
        return run_list

    @classmethod
    def group_multiple_runs(cls, group_by_key, runs):
        """
        Takes a list of dictionaries (ideally the output of `scan_multiple_runs`), and returns a dictionary
        of lists with
            - one key for every key present in any dictionary in `runs`.
            - one list as value for every such key (except `group_by_key`) with
                - one element for every item of `runs`, which may be None if the key does not belong to
                  a given run element.
            - if `group_by_key` is not None, one element for the key `group_by_key` which is the unique common
              non-None value for the key `group_by_key` among all the items of `runs`.
              (i.e. all the runs must have the same `group_by_key` value, or None, otherwise an exception is raised.)
        """
        all_keys = set()
        for i in xrange(0, len(runs)):
            # Make sure there is a dictionary in every entry
            if runs[i] is None:
                runs[i] = {}
            elif isinstance(runs[i], StatsExtractorBase):
                runs[i] = runs[i].as_dict()
            all_keys |= set(runs[i].keys())

        retval = {}
        for key in all_keys:
            if key == group_by_key:
                group_by_values = set([run[key] for run in runs if key in run])
                assert(len(group_by_values) == 1)
                retval[key] = group_by_values.pop()
            else:
                retval[key] = [None if key not in run else run[key] for run in runs]

        return retval

    @classmethod
    def quick_process_multiple_runs(cls, group_by_key, files):
        """
        Alias for scan_multiple_runs --> group_multiple_runs --> add_deltas_to_grouped_runs
        """
        return cls.add_deltas_to_grouped_runs(cls.group_multiple_runs(group_by_key, cls.scan_multiple_runs(files)))[0]

    @classmethod
    def add_deltas_to_grouped_runs(cls, *groups):
        """
        Each argument specified must be a dictionary. Returns a list of all the arguments.
        This method operates on only key-value pairs with list values.
        For a given list, all the items except the first are wrapped into a withdelta object,
        whose delta is computed by calling `get_delta_percent` with arguments resp. the first element of
        the list, and the currently processed item.
        In other words,

            key1            key2
            'common_value'  [55, 3, 4]

        will be transformed into

            key1            key2
            'common_value'  [55, withdelta(3, delta(55, 3)), withdelta(4, delta(55, 4))]
        """
        groups = list(groups)
        for i in xrange(0, len(groups)):
            for k in groups[i]:
                if type(groups[i][k]) is not list: continue
                ref_val = groups[i][k][0]
                groups[i][k] = [ref_val] + [withdelta(item, cls.get_delta_percent(ref_val, item)) for item in groups[i][k][1:]]
        return groups

    @classmethod
    def compute_footer_from_grouped_runs(cls, groups, with_delta=True):
        """
        Returns a dictionary with all the defined footer entries computed over the given `groups`.
        `groups` muts be a list of grouped runs (i.e. a list of dicts).

        Current implementation computed the maximum and the average and returns them as a dictionary
        with keys 'max' and 'avg'. The if `with_delta` is specified, deltas for max and avg are computed
        with `add_deltas_to_grouped_runs`.
        """
        class ExpandBinaryAction(object):
            def __call__(self, l, r):
                l, r = val_of(l), val_of(r)
                if type(l) is not type(r):
                    return None
                if type(l) is tuple:
                    return tuple(self(list(l), list(r)))
                if type(l) is list:
                    if len(l) < len(r): l, r = r, l
                    return [self(l[i], r[i]) for i in xrange(0, len(r))]
                if type(l) not in self.allowed_types:
                    return None
                return self.action(l, r)
            def __init__(self, action, allowed_types = [timedelta, float, int]):
                self.action, self.allowed_types = action, allowed_types

        class ExpandUnaryAction(object):
            def __call__(self, x):
                x = val_of(x)
                if type(x) is tuple:
                    return tuple(self(list(x)))
                if type(x) is list:
                    return [self(y) for y in x]
                if type(x) not in self.allowed_types:
                    return None
                return self.action(x)
            def __init__(self, action, allowed_types = [timedelta, float, int]):
                self.action, self.allowed_types = action, allowed_types

        def divide_value(x):
            if type(x) is timedelta:
                return timedelta(seconds=x.total_seconds() / float(len(groups)))
            elif type(x) is int:
                return int(x / float(len(groups)))
            else:
                return x / float(len(groups))

        custom_sum = ExpandBinaryAction(lambda s, t: s + t)
        custom_max = ExpandBinaryAction(lambda s, t: max(s, t))
        custom_divide = ExpandUnaryAction(divide_value)

        sums = {}
        maxes = {}

        for group in groups:
            for field in group:
                if not field in sums:
                    sums[field] = group[field]
                else:
                    sums[field] = custom_sum(sums[field], group[field])
                if not field in maxes:
                    maxes[field] = group[field]
                else:
                    maxes[field] = custom_max(maxes[field], group[field])
        for field in sums:
            sums[field] = custom_divide(sums[field])

        if with_delta:
            cls.add_deltas_to_grouped_runs(sums, maxes)

        return {'max': maxes, 'avg': sums}

    def __init__(self, file_handle):
        super(StatsExtractorBase, self).__init__()
        self.extracted_attributes = self.__class__.get_all_extracted_attributes()
        self.extractors = self.__class__.get_all_extractors()
        self._file_handle = file_handle

