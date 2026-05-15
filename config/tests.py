from smtplib import SMTPDataError, SMTPRecipientsRefused

from django.test import SimpleTestCase

from config.email_delivery import is_permanent_email_delivery_error


class EmailDeliveryErrorClassificationTest(SimpleTestCase):
    def test_recipient_4xx_is_retryable(self):
        recipient = "buyer@example.com"
        exc = SMTPRecipientsRefused({recipient: (450, b"4.2.0 Greylisted")})

        self.assertFalse(is_permanent_email_delivery_error(exc))

    def test_recipient_5xx_is_permanent(self):
        recipient = "buyer@example.com"
        response = b"5.1.1 Mailbox unavailable"
        exc = SMTPRecipientsRefused({recipient: (550, response)})

        self.assertTrue(is_permanent_email_delivery_error(exc))

    def test_mixed_recipient_codes_are_retryable(self):
        exc = SMTPRecipientsRefused(
            {
                "buyer@example.com": (451, b"4.7.1 Try again later"),
                "bad@example.com": (550, b"5.1.1 Mailbox unavailable"),
            }
        )

        self.assertFalse(is_permanent_email_delivery_error(exc))

    def test_smtp_response_5xx_is_permanent(self):
        exc = SMTPDataError(553, b"5.1.10 No valid recipients")

        self.assertTrue(is_permanent_email_delivery_error(exc))

    def test_smtp_response_4xx_is_retryable(self):
        exc = SMTPDataError(451, b"4.7.1 Try again later")

        self.assertFalse(is_permanent_email_delivery_error(exc))
