import re
import collections

from logster.logster_helper import (MetricObject, LogsterParser,
    LogsterParsingException)

class EventLogster(LogsterParser):

    def __init__(self, option_string=None):
        self.data = collections.defaultdict(lambda: 0)

    def EVENT(name, **params):
        return name, params

    def parse_line(self, line):
        '''
        Digest the contents of one line at a time, updating
        self's state variables. Takes a single argument, the line to be
        parsed.
        '''

        try:
            reg = 'EVENT\(.*\)'
            res = re.search(reg, line)
            if not res: return
            name, params = eval(res.group(), {}, vars(self.__class__))
            if 'surveyid' in params:
                name += '.' + str(params['surveyid'])
            self.data[name] += 1
        except Exception, e:
            raise LogsterParsingException(str(e))

    def get_state(self, duration):
        '''Run any necessary calculations on the data collected from the logs
        and return a list of metric objects.'''

        # Return a list of metrics objects
        return [MetricObject(name, self.data[name]) for name in self.data]
