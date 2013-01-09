from logster.parsers.PDLLogster import PDLLogster


class TestPDL(object):
    # Minimal correctness tests really
    # most of the PDL parser might be throw-away

    def setup(self):
        self.parser = PDLLogster()

    def test_no_matches(self):
        line = ""
        self.parser.parse_line(line)
        assert self.parser.data['servers'] == {}
        assert self.parser.data['callers'] == {}

    def test_match_server(self):
        line = " INFO [server_foo asdf-2134] CALL some_name(1, 1234)"
        self.parser.parse_line(line)
        assert self.parser.data['servers'] == {'server_foo': ['some_name']}
        assert self.parser.data['callers'] == {'some_name': ['server_foo']}

    def test_make_server_metric(self):
        line = " INFO [server_foo asdf-2134] CALL some_name(1, 1234)"
        self.parser.parse_line(line)
        result = self.parser.make_metric('servers')
        assert len(result) == 1

    def test_make_caller_metric(self):
        line = " INFO [server_foo asdf-2134] CALL some_name(1, 1234)"
        self.parser.parse_line(line)
        result = self.parser.make_metric('callers')
        assert len(result) == 1

