class BanterException(Exception):
    pass


class TxLineAuthError(BanterException):
    pass


class TxLineStreamError(BanterException):
    pass


class PaymentError(BanterException):
    pass


class BetValidationError(BanterException):
    pass


class NLUError(BanterException):
    pass
