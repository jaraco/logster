from logster.parsers.EventLogster import EventLogster


class TestEventLogster(object):

    @staticmethod
    def get_parser():
        return EventLogster()

    def test_match_simple_event(self):
        parser = self.get_parser()
        line = "EVENT('panman.email_send')"
        parser.parse_line(line)
        assert parser.data['panman.email_send'] == 1

    def test_survey_id(self):
        """
        Any event which indicates a 'surveyid' in the params should include
        it in the name of the event.
        """
        parser = self.get_parser()
        line = "EVENT('panman.email_send', surveyid=99)"
        parser.parse_line(line)
        assert parser.data['panman.email_send'] == 0
        assert parser.data['panman.email_send.99'] == 1
