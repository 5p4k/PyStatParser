"""
This module contains classes that format and produce outputs starting from the raw
scanned data.
"""
import string, math, cgi
from extractor import StatsExtractorBase
from withdelta import withdelta, val_of
from datetime import timedelta

def quick_html_escape(txt):
    """
    Performs a full escape of a string into valid HTML code, by
    replacing entities and quotes. Use for sanitizing output.
    """
    return cgi.escape(unicode(txt), quote=True).encode('ascii', 'xmlcharrefreplace')

class SimpleConsoleFormatter(object):
    """
    Prints to console the several runs in the format

    key1    value0  [value1  delta1  [value2  delta2 ...]]
    key2    ...

    Color coding is also used.
    """

    # We are going to need a bit of hand-weaving for formatting the output data because
    # unfortunately, these color characters *do* count when the length of a string is
    # extracted!! This messes up completely the usual python .format function.
    # We need to align colored text manually.
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    #BOLD = '\033[1m'
    #UNDERLINE = '\033[4m'

    runs_group = None

    key_colw = 4      # width of the key column
    value_colw = 6    # width of the value* column
    delta_colw = 8    # width of the delta* column

    def compute_key_len(self):
        """
        Stores the maximum length of the string representation of each key into
        `key_colw`. Retuns it.
        """
        for k in self.runs_group:
            self.key_colw = max(self.key_colw, len(k))
        return self.key_colw

    def compute_value_len(self):
        """
        Stores the maximum length of the string representation of each value into
        `value_colw`. Retuns it.
        """
        for k in self.runs_group:
            if type(self.runs_group[k]) is list:
                new_max = max([len(str(val_of(obj))) for obj in self.runs_group[k]])
            else:
                new_max = len(str(val_of(self.runs_group[k])))
            if new_max > self.value_colw:
                self.value_colw = new_max
        return self.value_colw

    def _create_header_and_output_format(self):
        def output_header(h, w, l_or_r = 'l'):
            padding = ' ' * (w - len(h))
            return \
                (padding + SimpleConsoleFormatter.HEADER + h + SimpleConsoleFormatter.ENDC) \
                if l_or_r == 'r' else \
                (SimpleConsoleFormatter.HEADER + h + SimpleConsoleFormatter.ENDC + padding)

        self._output_line_format = '{} {:>' + str(self.value_colw) + '}'
        if self._num_of_runs == 1:
            self._formatted_header = [output_header('NAME', self.key_colw, 'l'), output_header('VALUE', self.value_colw, 'r')]
        else:
            self._formatted_header = [output_header('NAME', self.key_colw, 'l'), output_header('VALUE0', self.value_colw, 'r')]
        for i in xrange(1, self._num_of_runs):
            self._output_line_format += ' {:>' + str(self.value_colw) + '} {}'
            self._formatted_header += [output_header('VALUE' + str(i), self.value_colw, 'r'), output_header('DELTA' + str(i), self.delta_colw, 'r')]

    def _generate_formatted_output(self):
        def output_percent(obj):
            f = None
            if type(obj) is withdelta:
                f = obj.delta
            if f is None:
                return self.delta_colw * ' '
            elif f != f:
                return (self.delta_colw - 3) * ' ' + 'n/a'
            elif f == 0.0:
                return (self.delta_colw - 1) * ' ' + '='
            else:
                as_string = '{:+0.1%}'.format(f)
                padding = ' ' * (self.delta_colw - len(as_string))
                if f > 0.05:
                    return padding + SimpleConsoleFormatter.FAIL + as_string + SimpleConsoleFormatter.ENDC
                elif f > 0.0:
                    return padding + SimpleConsoleFormatter.WARNING + as_string + SimpleConsoleFormatter.ENDC
                else:
                    return padding + SimpleConsoleFormatter.OKGREEN + as_string + SimpleConsoleFormatter.ENDC
        self._formatted_output = []
        for k in self.runs_group:
            self._formatted_output.append([SimpleConsoleFormatter.OKBLUE + k + SimpleConsoleFormatter.ENDC + ' ' * (self.key_colw - len(k))])
            if type(self.runs_group[k]) is list:
                self._formatted_output[-1].append(str(val_of(self.runs_group[k][0])))
                for val in self.runs_group[k][1:]:
                    self._formatted_output[-1] += [str(val_of(val)), output_percent(val)]
            else:
                self._formatted_output[-1].append(str(val_of(self.runs_group[k])))

    def run(self):
        """
        Prints to console the output.
        """
        if self._formatted_output is None:
            self.compute_key_len()
            self.compute_value_len()
            self._create_header_and_output_format()
            self._generate_formatted_output()

        print(' '.join(self._formatted_header))
        for line in self._formatted_output:
            print(self._output_line_format.format(*line))

    def __init__(self, runs_group):
        super(SimpleConsoleFormatter, self).__init__()
        self.runs_group = runs_group
        self._num_of_runs = max([len(self.runs_group[k]) for k in self.runs_group if type(self.runs_group[k]) is list])
        self._output_line_format = '<call _create_header_and_output_format>'
        self._formatted_header = ['<call _create_header_and_output_format>']
        self._formatted_output = None

class TableFormatterBase(object):
    """
        Base class for a more evolved formatter that can print stats in rows.
        All the begin_*, end_* and process_* methods should be overridden.
        The call stack for the `run` method is as follow:

        ```
        begin_table
            begin_header                        +loc_in_table(LOC_IN_TABLE_HDR)

                begin_row
                    begin_col                   +n_col, col_name, col_has_delta, value
                        begin_value             +loc_in_cell(LOC_IN_CELL_VALUE)
                            process_value
                        end_value
                        begin_delta             +loc_in_cell(LOC_IN_CELL_DELTA)
                            process_delta
                        end_delta               -loc_in_cell
                    end_col                     -n_col, col_name, col_has_delta, value
                end_row

            end_header
            begin_body                          +loc_in_table(LOC_IN_TABLE_BODY)

                begin_group                     -n_group, num_of_runs_in_group
                    begin_row                   +n_run
                        begin_col               +value, delta, num_of_runs_in_cell, col_has_delta, n_col, col_name
                            begin_value         +loc_in_cell(LOC_IN_CELL_VALUE)
                                process_value
                            end_value
                            begin_delta         +loc_in_cell(LOC_IN_CELL_DELTA)
                                process_delta
                            end_delta           -loc_in_cell
                        end_col                 -n_col, col_name, col_has_delta, value
                    end_row                     -n_run
                end_group                       -n_group, num_of_runs_in_group

            end_body                            -loc_in_table(LOC_IN_TABLE_BODY)
            begin_footer                        +loc_in_table(LOC_IN_TABLE_FOOTER)

                <same as body>

            end_footer                          -loc_in_table(LOC_IN_TABLE_FOOTER)
        end_table
        ```

        To each method, a Location object is passed as argument. The right column
        specifies which property is available at which time. More specifically
            - `+property(value)` means that the property is set before the call.
            - `-property` means that the property is reset after the call.
        Inspect the Location object to decide what to output.
        Each method is expected to return None if nothing must be printed, and
        a string othwerwise. No need to output a newline afterwards.

        The Location object passed should not be modified. Note that all these methods
        are always called, no matter whether the value/run/delta is available or not.
        It is up to the user to check the value of the properties in Location.

        The methods `recompute_header` and `column_has_delta` can be overridden to
        customize the class behaviour (hiding/sorting columns, deactivating the delta
        column). By default `column_has_delta` returns True if any value in the column
        has a delta.
    """

    class Location(object):
        """
        State object updated while printing the table.
        """
        LOC_IN_CELL_VALUE = 'LOC_IN_CELL_VALUE'
        LOC_IN_CELL_DELTA = 'LOC_IN_CELL_DELTA'
        LOC_IN_TABLE_HDR = 'LOC_IN_TABLE_HDR'
        LOC_IN_TABLE_BODY = 'LOC_IN_TABLE_BODY'
        LOC_IN_TABLE_FOOTER = 'LOC_IN_TABLE_FOOTER'

        loc_in_table = None
        n_group = -1
        n_col = -1
        col_name = None
        n_run = -1
        num_of_runs_in_cell = -1
        num_of_runs_in_group = -1
        value = None
        delta = None
        loc_in_cell = None
        col_has_delta = None

        def update(self, **kwargs):
            for k in kwargs:
                setattr(self, k, kwargs[k])
            return self

    table = None
    footer = None
    header = None
    footer_names = None

    def recompute_header(self, all_keys):
        """
        Returns a list of column names that constitute the header.
        """
        return sorted(list(all_keys))

    def column_has_delta(self, col_name):
        """
        Will be mapped to the `col_has_delta` property of the Location object.
        """
        return self._col_has_delta[col_name]

    def begin_table(self, loc):
        return None
    def begin_header(self, loc):
        return None
    def begin_body(self, loc):
        return None
    def begin_footer(self, loc):
        return None
    def begin_group(self, loc):
        return None
    def begin_row(self, loc):
        return None
    def begin_col(self, loc):
        return None
    def begin_value(self, loc):
        return None
    def begin_delta(self, loc):
        return None
    def process_value(self, loc):
        return None
    def process_delta(self, loc):
        return None
    def end_delta(self, loc):
        return None
    def end_value(self, loc):
        return None
    def end_col(self, loc):
        return None
    def end_row(self, loc):
        return None
    def end_group(self, loc):
        return None
    def end_body(self, loc):
        return None
    def end_footer(self, loc):
        return None
    def end_header(self, loc):
        return None
    def end_table(self, loc):
        return None

    def run(self):
        self.header = self.recompute_header(self._all_keys)

        self._output = ''
        def append(val):
            if val is None: return
            self._output += val + '\n'

        loc = self.__class__.Location()
        append(self.begin_table(loc))
        append(self.begin_header(loc.update(loc_in_table=loc.LOC_IN_TABLE_HDR)))
        append(self.begin_row(loc))
        for n_col in xrange(0, len(self.header)):
            append(self.begin_col(loc.update(
                value=self.header[n_col],
                n_col=n_col,
                col_has_delta=self.column_has_delta(self.header[n_col]),
                col_name=self.header[n_col]
            )))
            append(self.begin_value(loc.update(loc_in_cell=loc.LOC_IN_CELL_VALUE)))
            append(self.process_value(loc))
            append(self.end_value(loc))
            append(self.begin_delta(loc.update(loc_in_cell=loc.LOC_IN_CELL_DELTA)))
            append(self.process_delta(loc))
            append(self.end_delta(loc))
            append(self.end_col(loc.update(loc_in_cell=None)))
        append(self.end_row(loc.update(
            value=None,
            n_col=-1,
            col_has_delta=None,
            col_name=None,
        )))
        append(self.end_header(loc))
        append(self.begin_body(loc.update(loc_in_table=loc.LOC_IN_TABLE_BODY)))

        def process_groups(groups, group_offset = 0):
            for n_group in xrange(0, len(groups)):
                runs_in_group = self._num_of_runs_in_group[n_group + group_offset]
                append(self.begin_group(loc.update(
                    n_group=n_group,
                    num_of_runs_in_group=runs_in_group
                )))
                for n_run in xrange(0, runs_in_group):
                    append(self.begin_row(loc.update(n_run=n_run)))
                    for n_col in xrange(0, len(self.header)):
                        # account for missing columns
                        col_name = self.header[n_col]
                        runs_in_cell = -1
                        value = None
                        delta = None
                        if col_name in groups[n_group]:
                            runs_in_cell = self._num_of_runs_in_cell[n_group][col_name]
                            if runs_in_cell > 0:
                                value = groups[n_group][col_name][n_run]
                            else:
                                value = groups[n_group][col_name]
                            delta = value.delta if isinstance(value, withdelta) else None
                            value = val_of(value)

                        append(self.begin_col(loc.update(
                            value=value,
                            delta=delta,
                            num_of_runs_in_cell=runs_in_cell,
                            col_has_delta=self.column_has_delta(col_name),
                            n_col=n_col,
                            col_name=col_name
                        )))
                        append(self.begin_value(loc.update(loc_in_cell=loc.LOC_IN_CELL_VALUE)))
                        append(self.process_value(loc))
                        append(self.end_value(loc))
                        append(self.begin_delta(loc.update(loc_in_cell=loc.LOC_IN_CELL_DELTA)))
                        append(self.process_delta(loc))
                        append(self.end_delta(loc))
                        append(self.end_col(loc.update(loc_in_cell=None)))

                    append(self.end_row(loc.update(
                        value=None,
                        delta=None,
                        num_of_runs_in_cell=-1,
                        col_has_delta=None,
                        n_col=-1,
                        col_name=None
                    )))
                append(self.end_group(loc.update(n_run=-1)))

        process_groups(self.table)
        append(self.end_body(loc.update(n_group=-1, num_of_runs_in_group=-1)))
        append(self.begin_footer(loc.update(loc_in_table=loc.LOC_IN_TABLE_FOOTER)))
        process_groups(self.footer, len(self.table))
        append(self.end_footer(loc.update(n_group=-1, num_of_runs_in_group=-1)))
        append(self.end_table(loc.update(loc_in_table=None)))
        return self._output

    def _get_extra_info(self):
        self._all_keys = set()
        self._col_has_delta = {}
        self._num_of_runs_in_group = []
        self._num_of_runs_in_cell = []
        for group in self.table + self.footer:
            self._all_keys |= set(group.keys())
            self._num_of_runs_in_cell.append({})
            self._num_of_runs_in_group.append(-1)
            for k in group:
                if not k in self._col_has_delta:
                    self._col_has_delta[k] = False
                if type(group[k]) is list:
                    for val in group[k]:
                        if isinstance(val, withdelta):
                            self._col_has_delta[k] = True
                            break
                runs_in_cell = len(group[k]) if type(group[k]) is list else -1
                self._num_of_runs_in_cell[-1][k] = runs_in_cell
                if runs_in_cell > self._num_of_runs_in_group[-1]:
                    self._num_of_runs_in_group[-1] = runs_in_cell

    def __init__(self, grouped_runs, footer_with_delta=True):
        super(TableFormatterBase, self).__init__()
        self.table = grouped_runs
        candidate_footer = StatsExtractorBase.compute_footer_from_grouped_runs(grouped_runs, with_delta=footer_with_delta)
        self.footer_names = candidate_footer.keys()
        self.footer = [candidate_footer[k] for k in self.footer_names]
        self._get_extra_info()

class TableFilteredBase(TableFormatterBase):
    """
    Overrides TableFormatterBase to allow column sorting, extra column attribute storage,
    column filtering.

    Set the property `preferred_order` to a list of column names to sort them. These columns
    always appear before the columns that do not belong to the `preferred_order` list.

    The `column_descriptors` property is instead a dictionary of dictionary, where the second-level
    dicitonaries describe the attributes of the column.

    Some properties are already defined, that is `toggle_off` (which will remove the column from
    the header) and `toggle_delta_off` (which will force `column_has_delta` to return False)/
    """

    column_descriptors = {}
    preferred_order = []

    @classmethod
    def get_default_column_descriptor(cls):
        return {
            'toggle_off': False,
            'toggle_delta_off': False,
        }

    @classmethod
    def get_default_column_descriptors(cls):
        return {}

    @classmethod
    def get_default_preferred_order(cls):
        return []

    def set_column_attribute(self, col_name, attrib_name, value):
        if col_name not in self.column_descriptors:
            self.column_descriptors[col_name] = {}
        self.column_descriptors[col_name][attrib_name] = value

    def get_default_column_attribute(self, col_name, attrib_name):
        return self.__class__.get_default_column_descriptor()[attrib_name]

    def get_column_attribute(self, col_name, attrib_name, default=None):
        """
        Reads an attribute with name `attrib_name` from the descriptor of `col_name`.
        If there is no descriptor for `col_name`, the `default` is returned.
        """
        if col_name in self.column_descriptors:
            descriptor = self.column_descriptors[col_name]
        else:
            descriptor = self.__class__.get_default_column_descriptor()
        if attrib_name not in descriptor:
            return default
        else:
            return descriptor[attrib_name]

    def recompute_header(self, all_keys):
        exclude = [k for k in self.column_descriptors if self.get_column_attribute(k, 'toggle_off', False)]
        return [col for col in self.preferred_order if col in all_keys and col not in exclude] + \
               [col for col in all_keys if col not in exclude and col not in self.preferred_order]

    def column_has_delta(self, col_name):
        if self.get_column_attribute(col_name, 'toggle_delta_off', False):
            return False
        return super(TableFilteredBase, self).column_has_delta(col_name)

    def __init__(self, *args, **kwargs):
        super(TableFilteredBase, self).__init__(*args, **kwargs)
        self.column_descriptors = self.__class__.get_default_column_descriptors()
        self.preferred_order = self.__class__.get_default_preferred_order()

class TagBuilder(object):
    """
    Helper class for storing tag attributes and converting them properly to strings.
    """
    tag_name = 'span'
    attributes = {}
    classes = []
    body = None

    def preprocess(self):
        if self.classes is not None and len(self.classes) > 0:
            self.attributes['class'] = ' '.join(self.classes)
        elif 'class' in self.attributes:
            del self.attributes['class']

    def run(self):
        self.preprocess()
        opening = '<%s' % self.tag_name
        if len(self.attributes) > 0:
            opening += ' ' + ' '.join(['%s="%s"' % (k, quick_html_escape(self.attributes[k])) for k in self.attributes])
        opening += '>'
        closing = '</%s>' % self.tag_name
        return (opening, quick_html_escape(self.body) if self.body is not None else None, closing)

    @classmethod
    def create_tag(cls, tag_name, classes=[], body=None, **extra_attribs):
        builder = cls(tag_name)
        builder.attributes = extra_attribs
        builder.classes = classes
        builder.body = body
        opening, body, closing = builder.run()
        if body is not None:
            return opening + body + closing
        else:
            return opening

    def __init__(self, tag_name):
        super(TagBuilder, self).__init__()
        self.tag_name = tag_name
        self.attributes = {}
        self.classes = []
        self.body = None

class HTMLSheetFormatter(TableFilteredBase):
    """
    Produces an HTML5 table with Bootstrap contextual classes.

    If the first column does not have any run, it is considered as the main grouping criterion
    for the data and thus the first column data is rendered inside a TH instead of a TD.
    (i.e. if you group by 'object_name' and 'object_name' is the first column, then you will get the
    first column as THs).

    If such condition is met, then the footer will contain in the first column the label of the
    footer row instead of the value.

    This class automatically adds contextual classes text-info/warning/danger/success/muted to the
    deltas, which are rendered inside <small/>, where the success color depends on the attribute
    'bigger_is_better' of the column descriptor.

    If the attribute 'stand_out' is set to True, then contextual classes are added also to the cells,
    as well as the 'stand-out' class.

    All the delta cells have a 'delta' class.

    Optionally, the user can provide a formatter function as the column descriptor attribute 'formatter'
    to customize the output.
    See the module `formatters.py`.
    """
    title = 'HTMLSheetFormatter'
    run_names = []


    @classmethod
    def get_default_column_descriptor(cls):
        sup = super(HTMLSheetFormatter, cls).get_default_column_descriptor()
        sup.update({
            'stand_out': False,
            'formatter': None,
            'bigger_is_better': False
        })
        return sup

    @classmethod
    def get_default_template(cls):
        return string.Template('''
<!DOCTYPE html>
<html>
<head>
    <title>$title</title>
    <style>
        table.table > thead > tr:last-child > th {
            border-bottom-color: #999;
        }
        table.table > tbody > tr:last-child > td,
        table.table > tbody > tr:last-child > th {
            border-bottom: none;
        }
        table.table > tfoot > tr:first-child > th,
        table.table > tfoot > tr:first-child > td {
            border-top: 2px solid #999;
        }
        table.table tr > th[rowspan] {
            vertical-align: middle;
        }

        table.table > thead > tr > th.stand-out {
            border-left: 2px solid #444;
            border-right: 2px solid #444;
        }
        table.table > thead > tr:first-child > th.stand-out {
            border-top: 2px solid #444;
        }

        table.table > tfoot > tr:last-child > th.stand-out,
        table.table > tfoot > tr:last-child > td.stand-out {
            border-bottom: 2px solid #444;
        }
        table.table > tbody > tr > td.stand-out:not(.delta),
        table.table > tfoot > tr > td.stand-out:not(.delta) {
            border-left: 2px solid #444;
        }
        table.table > tbody > tr > td.stand-out.delta,
        table.table > tfoot > tr > td.stand-out.delta {
            border-right: 2px solid #444;
        }

        table.table-striped > tfoot > tr:nth-of-type(odd) {
            background-color: #f9f9f9;
        }
        table.table > tfoot > tr.as-tbody > th,
        table.table > tfoot > tr.as-tbody > td {
            border-top-width: 2px;
        }
        table.table > tfoot > tr > th {
            text-transform: uppercase;
        }
        table.table tr > td.text-muted,
        table.table tr > th.text-muted {
            overflow: hidden;
        }
        table.table tr > td,
        table.table tr > th {
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
        }
    </style>
</head>
<body>
    <h2>$title</h2>
    Run folders:
$run_names
$table
</body>
</html>
''')

    def begin_runs(self):
        return self.increase_indent() + '<ol>'
    def process_run(self, idx, name):
        return self.indent() + '<li>' + quick_html_escape(name) + '</li>'
    def end_runs(self):
        return self.decrease_indent() + '</ol>'

    def run(self):
        run_names = '    n/a' # :)
        if self.run_names is not None and len(self.run_names) > 0:
            self._indent = 1
            self._runs_output = ''
            def append(line):
                if line is not None:
                    self._runs_output += line + '\n'
            append(self.begin_runs())
            for i in xrange(0, len(self.run_names)):
                append(self.process_run(i, self.run_names[i]))
            append(self.end_runs())
            self._indent = 0
        return self.__class__.get_default_template().substitute({
            'run_names': self._runs_output,
            'title': quick_html_escape(self.title),
            'table': super(HTMLSheetFormatter, self).run()
        })

    def cell_is_th(self, loc):
        """
        True if the cell is a TH, false o/w. Returns True for headers and first column, if it ha no runs.
        """
        return loc.loc_in_table == loc.LOC_IN_TABLE_HDR or (loc.num_of_runs_in_cell <= 0 and loc.n_col == 0)

    def get_stand_out_class(self, loc):
        """
        Returns muted/warning/info/danger/success accordnig to the value of `loc.delta` and the column
        attribute 'bigger_is_better'.
        """
        if loc.delta is None:
            return 'muted'
        elif loc.delta != loc.delta:
            return None
        else:
            if self.get_column_attribute(loc.col_name, 'bigger_is_better', False):
                if loc.delta < -0.05:
                    return 'danger'
                elif loc.delta < 0.0:
                    return 'warning'
                elif loc.delta < 0.05:
                    return 'info'
                else:
                    return 'success'
            else:
                if loc.delta <= -0.05:
                    return 'success'
                elif loc.delta <= 0.0:
                    return 'info'
                elif loc.delta <= 0.05:
                    return 'warning'
                else:
                    return 'danger'

    def get_delta_text_and_classes(self, loc):
        """
        Converts `loc.delta` to a string and returns a tuple (str, list) containing the text of the delta
        and the contextual classes to be applied to the <small> tag.
        """
        as_string = None
        if loc.delta is None:
            as_string = 'n/a'
        elif loc.delta != loc.delta:
            as_string = None
        elif math.isinf(loc.delta):
            try:
                # retrieve the base value
                this_value = loc.value
                base_value = self.table[loc.n_group][loc.col_name][0]
                this_value -= base_value
                as_string = str(this_value)
                if this_value >= 0.0:
                    as_string = '+' + as_string
            except:
                as_string = '+INF' if loc.delta >= 0.0 else '-INF'
        else:
            as_string = '{:+0.1%}'.format(loc.delta)

        stand_out_class = self._get_stand_out_class_from_cache(loc)
        if stand_out_class is None:
            return (as_string, None)
        else:
            return (as_string, ['text-' + self._get_stand_out_class_from_cache(loc)])

    def begin_table(self, loc):
        return self.increase_indent() + '<table class="table table-condensed table-striped">'
    def end_table(self, loc):
        return self.decrease_indent() + '</table>'

    def begin_header(self, loc):
        return self.increase_indent() + '<thead>'
    def end_header(self, loc):
        return self.decrease_indent() + '</thead>'

    def begin_footer(self, loc):
        return self.increase_indent() + '<tfoot>'
    def end_footer(self, loc):
        return self.decrease_indent() + '</tfoot>'

    def begin_group(self, loc):
        if loc.loc_in_table != loc.LOC_IN_TABLE_BODY:
            return None
        return self.increase_indent() + '<tbody>'
    def end_group(self, loc):
        if loc.loc_in_table != loc.LOC_IN_TABLE_BODY:
            return None
        return self.decrease_indent() + '</tbody>'

    def begin_row(self, loc):
        if loc.loc_in_table == loc.LOC_IN_TABLE_FOOTER and loc.n_run == 0:
            return self.increase_indent() + '<tr class="as-tbody">'
        return self.increase_indent() + '<tr>'
    def end_row(self, loc):
        return self.decrease_indent() + '</tr>'

    def begin_value(self, loc):
        builder = TagBuilder('td')

        if self.cell_is_th(loc):
            builder.tag_name = 'th'
            if loc.loc_in_table == loc.LOC_IN_TABLE_FOOTER:
                builder.classes.append('text-muted')
                builder.classes.append('text-center')
            elif loc.loc_in_table == loc.LOC_IN_TABLE_HDR:
                builder.classes.append('text-center')
        else:
            builder.classes.append('text-right')

        if loc.loc_in_table == loc.LOC_IN_TABLE_HDR:
            if self.column_has_delta(loc.col_name):
                builder.attributes['colspan'] = 2

        if loc.num_of_runs_in_cell <= 0 and loc.num_of_runs_in_group > 0:
            if loc.n_run == 0:
                builder.attributes['rowspan'] = loc.num_of_runs_in_group
                if self.column_has_delta(loc.col_name):
                    builder.attributes['colspan'] = 2
            else:
                return None # skip

        if self.get_column_attribute(loc.col_name, 'stand_out', False):
            builder.classes.append('stand-out')
            if loc.loc_in_table != loc.LOC_IN_TABLE_HDR:
                stand_out_class = self._get_stand_out_class_from_cache(loc)
                if stand_out_class is not None and stand_out_class != 'muted':
                    builder.classes.append(stand_out_class)

        opening, _, _ = builder.run()
        return self.increase_indent() + opening

    def end_value(self, loc):
        if loc.num_of_runs_in_cell <= 0 and loc.num_of_runs_in_group > 0 and loc.n_run > 0:
            return None
        return self.decrease_indent() + ('</th>' if self.cell_is_th(loc) else '</td>')

    def process_value(self, loc):
        if loc.num_of_runs_in_cell <= 0 and loc.num_of_runs_in_group > 0 and loc.n_run > 0:
            return None

        value = loc.value
        if loc.loc_in_table != loc.LOC_IN_TABLE_HDR:
            formatter = self.get_column_attribute(loc.col_name, 'formatter', None)
            if formatter is not None:
                value = formatter(value)
        if loc.loc_in_table == loc.LOC_IN_TABLE_FOOTER:
            if loc.num_of_runs_in_cell <= 0 and loc.n_col == 0:
                value = self.footer_names[loc.n_group]

        if value is None:
            return self.indent() + '<span class="text-muted">n/a</span>'
        else:
            return self.indent() + quick_html_escape(str(value))

    def begin_delta(self, loc):
        if not self.column_has_delta(loc.col_name) or loc.loc_in_table == loc.LOC_IN_TABLE_HDR:
            return None
        if loc.num_of_runs_in_cell <= 0 and loc.num_of_runs_in_group > 0 and loc.n_run > 0:
            return None

        classes = ['delta']
        if self.get_column_attribute(loc.col_name, 'stand_out', False):
            classes.append('stand-out')
            stand_out_class = self._get_stand_out_class_from_cache(loc)
            if stand_out_class is not None and stand_out_class != 'muted':
                classes.append(stand_out_class)

        return self.increase_indent() + TagBuilder.create_tag('td', classes)

    def end_delta(self, loc):
        if not self.column_has_delta(loc.col_name) or loc.loc_in_table == loc.LOC_IN_TABLE_HDR:
            return None
        if loc.num_of_runs_in_cell <= 0 and loc.num_of_runs_in_group > 0 and loc.n_run > 0:
            return None
        return self.decrease_indent() + '</td>'

    def process_delta(self, loc):
        if not self.column_has_delta(loc.col_name) or loc.loc_in_table == loc.LOC_IN_TABLE_HDR:
            return None
        if loc.num_of_runs_in_cell <= 0 and loc.num_of_runs_in_group > 0 and loc.n_run > 0:
            return None
        if loc.n_run == 0:
            return None

        builder = TagBuilder('small')
        body, classes = self.get_delta_text_and_classes(loc)
        if body is None:
            return None
        else:
            builder.body = body
        if classes is not None:
            if type(classes) is not list:
                classes = [classes]
            builder.classes += classes

        opening, body, closing = builder.run()
        return self.indent() + opening + body + closing

    def _get_stand_out_class_from_cache(self, loc):
        key = (loc.n_group, loc.n_run, loc.n_col)
        if key not in self._stand_out_class_cache:
            self._stand_out_class_cache[key] = self.get_stand_out_class(loc)
        return self._stand_out_class_cache[key]

    def increase_indent(self):
        self._indent += 1
        return ' ' * 4 * (self._indent - 1)

    def decrease_indent(self):
        self._indent -= 1
        return self.indent()

    def indent(self):
        return ' ' * 4 * self._indent

    def __init__(self, grouped_runs, footer_with_delta=True, run_names=[], title='HTMLSheetFormatter'):
        super(HTMLSheetFormatter, self).__init__(grouped_runs, footer_with_delta)
        self._stand_out_class_cache = {}
        self._indent = 0
        self.run_names = run_names
        self.title = title
