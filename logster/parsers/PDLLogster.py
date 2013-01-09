import re
from logster.logster_helper import LogsterParser, LogsterParsingException, MetricObject


class PDLLogster(LogsterParser):

    def __init__(self, option_string=None):
        self.data = {'servers':{}, 'callers':{}}

    def parse_line(self, line):
        """
        Lines come in a format similar to:
        Month Day HH:MM:SS server logger: @some_hash YYYY-MM-DD HH:MM:SS,SSS\
        PROXY proxy LEVEL [caller hash-hash] CALL some_call(\d+, '\w+')
        """
        pattern = r'.*\s+INFO\s+\[(?P<server_id>\w+)\s+(?P<caller_hash>[a-zA-Z0-9_-]+)\]\s+CALL\s+(?P<caller_name>\w+)'
        regex = re.compile(pattern)
        match = regex.match(line)
        if not match:
            return False
        # Update self.data with collected metrics
        try:
            result = match.groupdict()
            server_id = result.get('server_id', 'default')
            caller_name = result.get('caller_name', 'default')
            self.data['servers'].setdefault(server_id, []).append(caller_name)
            self.data['callers'].setdefault(caller_name, []).append(server_id)
        except Exception, e:
            raise LogsterParsingException(str(e))

    def make_metric(self, metric_type):
        prefix = 'pdl.%s.' % metric_type
        return [
            MetricObject(prefix+name, len(items), 'Calls per server')
            for name, items in self.data[metric_type].iteritems()
        ]

    def get_state(self, duration):
        """
        Return 2 metrics: one for the server_id and one for the caller_name
        """
        self.duration = duration

        server_metrics = self.make_metric('servers')
        caller_metrics = self.make_metric('callers')

        return server_metrics + caller_metrics

