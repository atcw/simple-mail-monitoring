#!/usr/bin/env python3
import logging
import os
import traceback
import shutil
import sys
from datetime import datetime
from email import message_from_string
from email.mime.text import MIMEText
from email.utils import format_datetime, mktime_tz, parsedate_tz
from imaplib import IMAP4_SSL
from random import SystemRandom
from smtplib import SMTP
from string import ascii_letters, digits
from tempfile import NamedTemporaryFile
from time import sleep
from typing import Optional

import config

random = SystemRandom()


def check_delivery(metrics: dict):
    subject_identifier = ''.join(random.choice(ascii_letters + digits) for i in range(30))
    subject = config.TEST_MAIL['subject'].format(subject_identifier)

    before_send = datetime.now()
    send_test_message(subject)
    after_send = datetime.now()

    send_time_seconds = (after_send - before_send).total_seconds()
    metrics['send_time_seconds'] = send_time_seconds

    retry = 0
    while True:
        sleep(2)

        logging.info('trying to fetch test mail, retry %s', retry)
        date = get_email_date(subject)
        if date:
            break
        retry += 1
        if retry > config.MAX_RETRIES:
            logging.error('failed to fetch test mail')
            return

    if not date:
        logging.error('failed to get the date of the last email')
        return

    after_receive = datetime.now()
    receive_time_seconds = (after_receive - after_send).total_seconds()
    metrics['receive_time_seconds'] = receive_time_seconds

    metrics['mail_timestamp'] = date.timestamp()

    metrics['success'] = True


def get_email_date(subject: str) -> Optional[datetime]:
    """
    Get the date of the email with specified subject and delete it.

    Warning: no escaping of subject is performed.
    """
    most_recent_date = None

    with IMAP4_SSL(config.IMAP['host']) as conn:
        conn.login(config.IMAP['user'], config.IMAP['password'])
        conn.select(config.IMAP['mailbox'])

        logging.info('connected to mailbox %s', config.IMAP['mailbox'])

        state, matches = conn.search(None, '(SUBJECT "{}")'.format(subject))
        if state != 'OK':
            logging.error('failure listing messages')
            return
        matches = [match for match in matches[0].split(b' ') if match]
        logging.info('found %s matching message(s)', len(matches))
        for match in matches:
            state, msg = conn.fetch(match, '(RFC822)')
            if state != 'OK':
                logging.error('failure fetching message')
                return
            msg = message_from_string(msg[0][1].decode())
            msg_date = datetime.fromtimestamp(
                mktime_tz(parsedate_tz(msg['Date'])))
            logging.info('fetched message %s, date %s', int(match), msg_date)

            if most_recent_date is None or msg_date > most_recent_date:
                most_recent_date = msg_date

            conn.store(match, '+FLAGS', '\\Deleted')

        logging.info('expunging mailbox')
        conn.expunge()

    return most_recent_date


def send_test_message(subject: str):
    mail = MIMEText(
        'This is a test email. Its sole purpose is to act as a test email\n'
        'whose existence will confirm that email delivery is working\n'
        'as it should.')
    mail['Subject'] = subject
    mail['From'] = config.TEST_MAIL['sender']
    mail['To'] = config.TEST_MAIL['recipient']
    mail['Date'] = format_datetime(datetime.utcnow())

    try:
        with SMTP(config.SMTP['host'], config.SMTP['port']) as smtp:
            smtp_user = config.SMTP.get('user')
            smtp_password = config.SMTP.get('password')
            smtp_tls = config.SMTP.get('tls')
            if smtp_tls:
              smtp.starttls()
            if smtp_user and smtp_password:
              smtp.login(smtp_user, smtp_password)
      
            smtp.sendmail(
              config.TEST_MAIL['sender'],
              config.TEST_MAIL['recipient'],
              mail.as_string())
            logging.info('sent test email with subject "%s"', subject)
    except:
        send_panic_message("smtpd not running on 25")


def send_panic_message(subject: str):
    mail = MIMEText(
        'email not working'
        '')
    mail['Subject'] = subject
    mail['From'] = config.PANIC_MAIL['sender']
    mail['To'] = config.PANIC_MAIL['recipient']
    mail['Date'] = format_datetime(datetime.utcnow())
    with SMTP(config.PANIC_SMTP['host'], config.PANIC_SMTP['port']) as smtp:
        smtp_user = config.PANIC_SMTP.get('user')
        smtp_password = config.PANIC_SMTP.get('password')
        smtp_tls = config.PANIC_SMTP.get('tls')
        if smtp_tls:
            smtp.starttls()
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)

        smtp.sendmail(
            config.PANIC_MAIL['sender'],
            config.PANIC_MAIL['recipient'],
            mail.as_string())
    logging.info('sent panic email with subject "%s"', subject)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)-15s: %(message)s', level=config.LOG_LEVEL)

    start = datetime.now()

    metrics = {}

    try:
        check_delivery(metrics)
    except Exception:
        logging.error('a failure occured: %s', traceback.format_exc())
        metrics = {
            'success': False
        }

    end = datetime.now()
    metrics['total_duration'] = (end - start).total_seconds()
    
    if not 'success' in metrics.keys():
    #if not metrics['success'] :
       logging.error('email roundtrip error - exit code has been set see echo $?')
       send_panic_message("email roundtrip delivery failed")
       logging.error('sent panic mail')
       #sys.exit(-500)
       sys.exit(os.EX_UNAVAILABLE)
    #test panic message
    #send_panic_message("email roundtrip delivery failed")
    sys.exit(0)
# fix tabs to space with vim :%s/\t/  /g
# vim: tabstop=2 shiftwidth=2 expandtab
