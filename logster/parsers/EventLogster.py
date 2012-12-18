import re

from logster.logster_helper import (MetricObject, LogsterParser,
    LogsterParsingException)

class EventParser(LogsterParser):

    def __init__(self, option_string=None):
        self.data = {}

    def EVENT(name, **items):
        return name, items

    def parse_line(self, line):
        '''
        Digest the contents of one line at a time, updating
        self's state variables. Takes a single argument, the line to be
        parsed.
        '''

        try:
            reg = 'EVENT\(.*\)'
            res = re.search(reg, line)
            name, items = eval(res.group(), vars(self.__class__))
            self.data.setdefault(name, []).append(items)
        except Exception, e:
            raise LogsterParsingException(str(e))

    def get_state(self, duration):
        '''Run any necessary calculations on the data collected from the logs
        and return a list of metric objects.'''
        self.duration = duration

        # Return a list of metrics objects
        return [
            MetricObject(name, len(items) / duration, "Hz")
            for name, items in self.data
        ]
