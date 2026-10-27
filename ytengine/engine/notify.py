"""Daily status message: email (lands on your phone too) and optional Telegram."""
import smtplib, ssl
from email.message import EmailMessage
from pathlib import Path
from .config import env
from .util import http, log


def email(subject, body, attachments=(), to=None):
    host, user, pw = env('SMTP_HOST', 'smtp.gmail.com'), env('SMTP_USER'), env('SMTP_PASS')
    to = to or env('NOTIFY_EMAIL_TO') or user
    if not (user and pw and to):
        log.info('email not configured; skipping notification'); return False
    m = EmailMessage(); m['Subject'] = subject; m['From'] = user; m['To'] = to
    m.set_content(body)
    for a in attachments:
        p = Path(a)
        if p.exists() and p.stat().st_size < 8_000_000:
            m.add_attachment(p.read_bytes(), maintype='image', subtype='jpeg' if p.suffix.lower() in ('.jpg', '.jpeg') else 'png', filename=p.name)
    try:
        with smtplib.SMTP_SSL(host, int(env('SMTP_PORT', '465')), context=ssl.create_default_context()) as s:
            s.login(user, pw); s.send_message(m)
        return True
    except Exception as e:
        log.error('email failed: %s', e); return False


def telegram(text, photo=None):
    tok, chat = env('TELEGRAM_BOT_TOKEN'), env('TELEGRAM_CHAT_ID')
    if not (tok and chat): return False
    try:
        if photo and Path(photo).exists():
            with open(photo, 'rb') as f:
                http('POST', f'https://api.telegram.org/bot{tok}/sendPhoto', data={'chat_id': chat, 'caption': text[:1000]}, files={'photo': f})
        else:
            http('POST', f'https://api.telegram.org/bot{tok}/sendMessage', data={'chat_id': chat, 'text': text[:4000]})
        return True
    except Exception as e:
        log.error('telegram failed: %s', e); return False


def send(cfg, subject, body, attachments=()):
    email(subject, body, attachments, cfg['notify'].get('email_to') or None)
    if cfg['notify'].get('telegram'): telegram(subject + '\n\n' + body, attachments[0] if attachments else None)
