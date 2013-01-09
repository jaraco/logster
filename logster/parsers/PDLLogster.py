import re
from logster.logster_helper import LogsterParser, LogsterParsingException


class PDLLogster(LogsterParser):

    def __init__(self):
        self.data = {}


    def parse_line(self, line):
        """
        Lines come in a format similar to:
        Jan  8 20:56:56 pdl01 logger: @4000000050ec8822393be4c4 2013-01-08 20:56:56,959 PROXY proxy         INFO     [sampling 3a9141d1-3eb2-4b4c-9e2e-2153d086fb1c] CALL get_answers(
        Ene  1 11:11:11 srv01 logger: @0000000000sdf789sad9f876 2012-01-01
        Month Day HH:MM:SS server logger: @some_hash YYYY-MM-DD HH:MM:SS,SSS PROXY proxy LEVEL [caller hash-hash] CALL some_call(\d+, '\w+')
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
            self.data.setdefault(server_id, []).append(caller_name)
            self.data.setdefault(caller_name, []).append(server_id)
        except Exception, e:
            raise LogsterParsingException(str(e))

    def get_state(self, duration):
        """
        Return 2 metrics: one for the server_id and one for the caller_name
        """

