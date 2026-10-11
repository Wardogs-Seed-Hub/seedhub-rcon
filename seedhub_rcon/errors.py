class Problem(Exception):
    def __init__(self, status, code, message, retry=None):
        super().__init__(code)
        self.status, self.code, self.message, self.retry = status, code, message, retry
