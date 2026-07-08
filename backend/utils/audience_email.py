from utils.email_delivery import send_email


WELCOME_SUBJECT = 'Welcome to BaseballOS bullpen notes'
WELCOME_TEXT = """Thanks for following BaseballOS.

You will get occasional bullpen notes and product updates as the project grows.

No picks. No betting. Just bullpen context and product updates.
"""
WELCOME_HTML = """
<p>Thanks for following BaseballOS.</p>
<p>You will get occasional bullpen notes and product updates as the project grows.</p>
<p>No picks. No betting. Just bullpen context and product updates.</p>
"""


def send_audience_welcome_email(email):
    return send_email(
        email,
        WELCOME_SUBJECT,
        text=WELCOME_TEXT,
        html=WELCOME_HTML,
        kind='audience_welcome',
    )
