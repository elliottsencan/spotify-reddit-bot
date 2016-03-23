import traceback
import praw
import config
import time
import sqlite3
import getpass
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email import Encoders
import os

'''CONFIGURATION'''


USERAGENT = config.app_ua
APP_ID = config.app_id
APP_SECRET = config.app_secret
APP_URI = config.app_uri
APP_REFRESH = config.app_refresh
SUBREDDIT = config.app_subreddits
KEYWORDS = ["spotify", "playlist"]
KEYAUTHORS = []
MAILME_RECIPIENT = "hollywoodprinciple"
MAILME_SUBJECT = "Spotify Playlist Found"
MAILME_ERROR_SUBJECT = "Spofify_bot.py error"
MAILME_MESSAGE = "[/u/_author_ said these keywords in /r/_subreddit_: _results_](_permalink_)"
MULTIPLE_MESSAGE_SEPARATOR = '\n\n_______\n\n'
MAXPOSTS = 100
WAIT = 30
gmail_user = os.environ['GMAIL_USER']
gmail_pwd =  os.environ['GMAIL_PWD']

DO_COMMENTS = True
DO_SUBMISSIONS = True
# Should check submissions and / or comments?

PERMALINK_SUBMISSION = 'https://reddit.com/r/%s/comments/%s'
PERMALINK_COMMENT = 'https://reddit.com/r/%s/comments/%s/_/%s'

CLEANCYCLES = 1000000
# After this many cycles, the bot will clean its database
# Keeping only the latest (2*MAXPOSTS) items

'''All done!'''

try:
    import bot
    USERAGENT = bot.aG
    APP_ID = bot.oG_id
    APP_SECRET = bot.oG_secret
    APP_URI = bot.oG_uri
    APP_REFRESH = bot.oG_scopes['all']
except ImportError:
    pass

sql = sqlite3.connect('sql.db')
cur = sql.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS oldposts(id TEXT)')
sql.commit()

print('Logging in...')
r = praw.Reddit(USERAGENT)
r.set_oauth_app_info(APP_ID, APP_SECRET, APP_URI)
r.refresh_access_information(APP_REFRESH)

KEYWORDS = [k.lower() for k in KEYWORDS]


def login(user, password):
   gmail_user = user
   gmail_pwd = password

def mail(to, subject, text, attach=None):
   msg = MIMEMultipart()
   msg['From'] = gmail_user
   msg['To'] = to
   msg['Subject'] = subject
   msg.attach(MIMEText(text))
   if attach:
      part = MIMEBase('application', 'octet-stream')
      part.set_payload(open(attach, 'rb').read())
      Encoders.encode_base64(part)
      part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(attach))
      msg.attach(part)
   mailServer = smtplib.SMTP("smtp.gmail.com", 587)
   mailServer.ehlo()
   mailServer.starttls()
   mailServer.ehlo()
   mailServer.login(gmail_user, gmail_pwd)
   mailServer.sendmail(gmail_user, to, msg.as_string())
   mailServer.close()

def mailme():
    print('Searching %s.' % SUBREDDIT)
    subreddit = r.get_subreddit(SUBREDDIT)
    
    posts = []
    if DO_SUBMISSIONS:
        print('Collecting submissions')
        posts += list(subreddit.get_new(limit=MAXPOSTS))
    if DO_COMMENTS:
        print('Collecting comments')
        posts += list(subreddit.get_comments(limit=MAXPOSTS))

    posts.sort(key= lambda x: x.created_utc)

    # Collect all of the message results into a list, so we can
    # package it all into one PM at the end
    message_results = []

    for post in posts:
        # Anything that needs to happen every loop goes here.
        pid = post.id

        try:
            pauthor = post.author.name
        except AttributeError:
            # Author is deleted. We don't care about this post.
            continue

        if r.has_scope('identity'):
            myself = r.user.name.lower()
        else:
            myself = ''

        if pauthor.lower() in [myself, MAILME_RECIPIENT.lower()]:
            print('Will not reply to myself.')
            continue

        if KEYAUTHORS != [] and all(auth.lower() != pauthor for auth in KEYAUTHORS):
            # The Kayauthors list has names in it, but this person
            # is not one of them.
            continue

        cur.execute('SELECT * FROM oldposts WHERE ID=?', [pid])
        if cur.fetchone():
            # Post is already in the database
            continue

        cur.execute('INSERT INTO oldposts VALUES(?)', [pid])
        sql.commit()

        subreddit = post.subreddit.display_name
        # I separate the permalink defnitions because they tend to consume
        # API calls despite not being technically required.
        # So I'll do it myself.
        if isinstance(post, praw.objects.Submission):
            pbody = '%s\n\n%s' % (post.title.lower(), post.selftext.lower())
            permalink = PERMALINK_SUBMISSION % (subreddit, post.id)
        
        elif isinstance(post, praw.objects.Comment):
            pbody = post.body.lower()
            link = post.link_id.split('_')[-1]
            permalink = PERMALINK_COMMENT % (subreddit, link, post.id)

        # Previously I used an if-any check, but this way allows me
        # to include the matches in the message text.
        matched_keywords = []
        for key in KEYWORDS:
            if key not in pbody:
                continue
            matched_keywords.append(key)
        if len(matched_keywords) == 0:
            continue

        if pauthor == "AutoModerator":
            continue

        message = MAILME_MESSAGE
        message = message.replace('_author_', pauthor)
        message = message.replace('_subreddit_', subreddit)
        message = message.replace('_id_', pid)
        message = message.replace('_permalink_', permalink)
        if '_results_' in message:
            matched_keywords = [('"%s"' % x) for x in matched_keywords]
            matched_keywords = '[%s]' % (', '.join(matched_keywords))
            message = message.replace('_results_', matched_keywords)

        message_results.append(message)

    if len(message_results) == 0:
        return

    print('Sending MailMe message with %d results' % len(message_results))
    message = MULTIPLE_MESSAGE_SEPARATOR.join(message_results)
    login(gmail_user, gmail_pwd)
    mail("hollywoodprinciple@gmail.com", MAILME_SUBJECT, message)


cycles = 0
if (DO_SUBMISSIONS, DO_COMMENTS) == (False, False):
    raise Exception('do_comments and do_submissions cannot both be false!')
while True:
    try:
        mailme()
        cycles += 1
    except Exception as e:
        mail("hollywoodprinciple@gmail.com", MAILME_ERROR_SUBJECT, traceback.print_exc())
        traceback.print_exc()
    if cycles >= CLEANCYCLES:
        print('Cleaning database')
        cur.execute('DELETE FROM oldposts WHERE id NOT IN (SELECT id FROM oldposts ORDER BY id DESC LIMIT ?)', [MAXPOSTS * 2])
        sql.commit()
        cycles = 0
    print('Running again in %d seconds \n' % WAIT)
    time.sleep(WAIT)

