# Python standard libraries
import datetime
import secrets
import json
import os
import time
import math
import re
import logging
import functools
import pprint
import copy

# Third-party libraries
from flask import Flask, redirect, render_template, url_for, session, request, abort

from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from flask_wtf import FlaskForm
from wtforms.fields import StringField, TextAreaField, HiddenField, RadioField, SubmitField, BooleanField
from wtforms import validators

from flask_babel import Babel, _, ngettext, lazy_gettext, lazy_ngettext, format_date, format_datetime, force_locale as babel_force_locale

from flask_talisman import Talisman

from authlib.integrations.flask_client import OAuth

from azure.cosmos import CosmosClient

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

import deepl

import requests

# Internal imports
import _stuffimporter
from user import User

# Logging
# Mise en place du système de logs avec impression dans la console et enregistrement dans un fichier logs.log
fh = logging.FileHandler("logs.log", encoding='utf-8')
formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s : %(message)s")
fh.setFormatter(formatter)

# Flask app setup
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)
app.logger.addHandler(fh)
app.logger.level = logging.INFO

app.logger.info("Lancement de l'application.")

# testing
testing = os.path.isdir("tests")
brod_change_threshold = 24 * 60 * 60
if testing:
    app.logger.level = logging.DEBUG
    app.logger.debug("Mode test activé.")

    from tests.ip_getter import get_ip
    app.config["SERVER_NAME"] = get_ip() + ":5000"

    with open(f"./tests/config.json", "r", encoding="utf-8") as json_file:  # Config setup
        config = json.load(json_file)
else:
    app.config["SERVER_NAME"] = "rbs.azurewebsites.net"

    config = _stuffimporter.StuffImporter.get_config()  # Config setup

# User session management setup
login_manager = LoginManager(app)

# Setting anonymous user


def anon_user_getter():
    anon_user = User()
    anon_user.is_active = False
    anon_user.is_authenticated = False
    anon_user.is_anonymous = True
    return anon_user


login_manager.anonymous_user = anon_user_getter

# Deepl translation setup
translator = deepl.Translator(config["deepl_auth_key"])

LANGUAGE_CODES = [lang.code.lower() for lang in translator.get_source_languages()]
SUPPORTED_LANGUAGES = ["en", "fr"]
app.logger.debug("Traducteur mis en place.")

# Internationalization setup


def get_lang():
    lang = request.args.get("lang")
    if lang and lang in LANGUAGE_CODES:
        session["lang"] = lang
        return lang
    elif session.get("lang") in LANGUAGE_CODES:
        return session["lang"]
    elif current_user.is_authenticated:
        return current_user.lang

    return request.accept_languages.best_match(SUPPORTED_LANGUAGES)


babel = Babel(app, locale_selector=get_lang)

# Database setup
cc = CosmosClient(config["db"]["url"], config["db"]["key"])
db = cc.get_database_client("Main Database")
user_container = db.get_container_client("Web RBS Users")
post_container = db.get_container_client("Web RBS Posts")
stats_cont = db.get_container_client("Web RBS Stats")

app.logger.debug("Base de donnée mise en place.")

stuffimporter = _stuffimporter.StuffImporter(stats_cont, _, ngettext)

# Stats setup
global stats
stats = stuffimporter.get_stats()
stats["time"]["start_time"] = time.time()
stuffimporter.set_stats(stats)
app.logger.debug("Stats récupérés.")

# Mail client setup
sg_client = SendGridAPIClient(config["sendgrid_api_key"])
app.logger.debug("Client mail mis en place.")

# OAuth setup
oauth = OAuth(app)

# Talisman (safe stuff)
csp = {
    "default-src": "'none'",
    "object-src": "'none'",
    "frame-ancestors": "'none'",
    "script-src": "'self'",
    "style-src": "'self'",
    "form-action": "'self'",
    "media-src": "'self'",
    "frame-src": [
        "'self'",
        "web-rbs.betteruptime.com"
    ],
    "base-uri": "'self'",
    "connect-src": "'self'",
    "report-to": {
        "group": "csp-endpoint",
        "max_age": 10886400,
        "endpoints": [
            {"url": "https://rbs.azurewebsites.net/report-csp-violations"}
        ]
    },
    "font-src": [
        "'self'",
        "data:"
    ],
    "img-src": [
        "'self'",
        "img.shields.io"
    ]
}
talisman = Talisman(
    app,
    content_security_policy=csp,
    content_security_policy_nonce_in=[
        "script-src",
        "style-src"
    ]
)

app.logger.info("Application lancée.")

# Flask-Login helper to retrieve a user from our db


@login_manager.user_loader
def load_user(user_id, active=True):
    user = User()
    if not user.uimport(user_container, user_id):
        return None

    # Check special roles
    if user_id in stats["roles"]["broadcaster"]:
        user.is_broadcaster = True
    elif user_id in stats["roles"]["preselecteds"]:
        user.is_preselected = True

    if user_id in stats["roles"]["admin"]:
        user.is_admin = True
    elif user_id in stats["roles"]["moderators"]:
        user.is_moderator = True

    # Used for stats
    if active:
        user.last_active = time.time()
        user.uexport(user_container)

    return user

# Useful defs


def send_mail(mail):
    if testing:
        print(f"Mail envoyé avec le sujet \"{mail.subject}\"")
    else:
        sg_client.send(mail)


def role_required(role):  # custom view decorator
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not request or app.config.get("LOGIN_DISABLED"):
                pass
            elif current_user.get_id() not in stats["roles"][role]:
                if role == "admin":
                    app.logger.warning(f"{current_user.get_id()} a trouvé le lien du panneau admin.")
                return abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_rem_secs():
    if stats["broadcast"]["content"]:
        rem_secs = stats["broadcast"]["_ts"] + brod_change_threshold - time.time()
    else:
        rem_secs = stats["time"]["last_broadcaster"] + brod_change_threshold - time.time()

    return rem_secs

# Custom template filters


@app.template_filter("format_date")
def template_format_date(ts, format=None):
    return format_date(datetime.datetime.utcfromtimestamp(ts), format=format)


@app.before_request
def verify_broadcast():
    if testing:
        return

    skip_save = False
    if stats["broadcast"]["content"] == "[deleted]" and stats["broadcast"]["author_name"] == "[deleted]":
        skip_save = True
    else:
        if not stats["broadcast"]["content"]:
            if stats["time"]["last_broadcaster"] + brod_change_threshold > time.time():
                app.logger.debug(f"Le diffuseur a toujours le temps pour faire sa diffusion.")
                return
            else:  # broadcaster didn't make his broadcast in time
                skip_save = True

                f_brod = load_user(stats["roles"]["broadcaster"][0], active=False)

                stats["roles"]["preselecteds"][f_brod.get_id()] = time.time()

                # Send former broadcaster the missed mail and setup the reselection proposal
                with app.app_context(), babel_force_locale(f_brod.lang):
                    message = Mail(
                        from_email="random.broadcasting.selector@gmail.com",
                        to_emails=f_brod.email,
                        subject=_("RandomBroadcastingSelector: You missed your opportunity but don't worry."),
                        html_content=render_template("mails/missed.html", server_name=app.config["SERVER_NAME"])
                    )
                send_mail(message)

                # check if some of the preselecteds have timed out
                for key, val in copy.deepcopy(stats["roles"]["preselecteds"]).items():
                    if val + 2592000 < time.time():  # if its been a month remove them
                        stats["roles"]["preselecteds"].pop(key)

        elif stats["broadcast"]["_ts"] + brod_change_threshold > time.time():
            app.logger.debug("Le post a toujours le temps d'être évalué.")
            return

    if not skip_save:  # Save current post
        with open("samples/sample_post.json", "r", encoding="utf-8") as sample_file:
            new_post = json.load(sample_file)

        new_post["id"] = stats["broadcast"]["id"]
        new_post["content"] = stats["broadcast"]["content"]
        new_post["author"] = stats["broadcast"]["author"]
        new_post["author_name"] = stats["broadcast"]["author_name"]
        new_post["lang"] = stats["broadcast"]["lang"]
        new_post["upvotes"] = stats["broadcast"]["upvotes"]
        new_post["downvotes"] = stats["broadcast"]["downvotes"]
        try:
            new_post["ratio"] = new_post["upvotes"] / new_post["downvotes"]
        except ZeroDivisionError:
            new_post["ratio"] = new_post["upvotes"]
        post_container.create_item(new_post)

        # Update stats in relation of the current post
        stats["broadcasts"]["msgs_sent"]["total"] += 1
        try:
            stats["broadcasts"]["msgs_sent"][new_post["lang"]] += 1
        except KeyError:
            stats["broadcasts"]["msgs_sent"][new_post["lang"]] = 1

        stats["broadcasts"]["words_sent"] += len(re.findall(r"[\w']+", new_post["content"]))  # add number of words
        stats["broadcasts"]["characters_sent"] += len(new_post["content"])  # add number of chars

    # Select another broadcaster
    if stats["roles"]["futur_broadcasters"]:
        stats["roles"]["broadcaster"] = [stats["roles"]["futur_broadcasters"].pop(0)]
    else:
        stats["roles"]["broadcaster"] = [stuffimporter.select_random_broadcaster(user_container, stats["roles"]["broadcaster"][0])]
    stats["broadcast"]["author"] = ""
    stats["broadcast"]["author_name"] = ""
    stats["broadcast"]["content"] = ""
    stats["broadcast"]["trads"] = {}
    stats["broadcast"]["upvotes"] = 0
    stats["broadcast"]["downvotes"] = 0
    stats["broadcast"]["reports"] = 0

    stats["time"]["last_broadcaster"] = time.time()

    broadcaster = load_user(stats["roles"]["broadcaster"][0], active=False)

    # Send mail to the new broadcaster
    with app.app_context(), babel_force_locale(broadcaster.lang):
        message = Mail(
            from_email="random.broadcasting.selector@gmail.com",
            to_emails=broadcaster.email,
            subject=_("RandomBroadcastingSelector: You are the one."),
            html_content=render_template("mails/broadcaster.html", server_name=app.config["SERVER_NAME"])
        )
    send_mail(message)

    stuffimporter.set_stats(stats)

    app.logger.info(f"Nouveau diffuseur {broadcaster.get_id()} a été sélectionné.")
    return


def login_or_create_user(id_: str, name: str, email: str, lang: str):
    if lang not in LANGUAGE_CODES:
        lang = request.accept_languages.best_match(LANGUAGE_CODES)

    # Test to see if the user exists in the db
    user = load_user(id_)

    return_val = redirect(url_for("index"))
    if not user:  # Doesn't exist? Add it to the database.
        try:
            fraud_id = user_container.query_items(f"SELECT u.id FROM Users u WHERE u.email = '{email}'", enable_cross_partition_query=True).next()
            app.logger.info(f"Double compte de {fraud_id} empéché.")
            return render_template("message.html", message=_("Double accounts aren't allowed."))
        except StopIteration:
            pass

        new_user = User(id_=id_, name=name, email=email, lang=lang)
        new_user.last_active = time.time()
        new_user.uexport(user_container)

        stats["users"]["num"] += 1
        stuffimporter.set_stats(stats)

        user = new_user

        app.logger.info(f"L'utilisateur {user.get_id()} a été créé.")

        return_val = render_template("message.html", message=_("You have successfully created your account, if you are selected, you will receive an email on %(mail)s so check your emails regularly.", mail=user.email))

    if user.banned:  # if user banned send the ban appeal form
        code = secrets.token_urlsafe(32)
        stats["roles"]["ban_appealers"][user.get_id()] = code
        stuffimporter.set_stats(stats)

        return redirect(url_for("ban_appeal", user_id=user.get_id(), appeal_code=code))

    # Begin user session by logging the user in
    user.is_authenticated = True
    login_user(user)

    # Send user back to homepage
    return return_val

# Routing


@app.route("/", methods=["GET", "POST"])
def index():
    form = ReportForm()

    if form.validate_on_submit():  # Report callback
        if not stats["broadcast"]["content"]:
            app.logger.warning(f"{current_user.get_id()} a essayé de signaler un post alors qu'il n'y en a pas.")
            return render_template("message.html", message=_("No post is live right now so you can't report one."))
        elif current_user.report_post_id == stats["broadcast"]["id"]:
            app.logger.debug(f"{current_user.get_id()} a essayé de resignaler le post.")
            return render_template("message.html", message=_("You have already reported this post so you can't report it again."))

        current_user.report_post_id = stats["broadcast"]["id"]
        current_user.report_reason = form.reason.data
        current_user.report_quote = form.message_quote.data

        current_user.uexport(user_container)

        stats["broadcast"]["reports"] += 1

        if stats["users"]["seen_msg"] > (3 * math.sqrt(stats["users"]["num"])) and stats["broadcast"]["reports"] > (stats["users"]["seen_msg"] / 2):  # ban condition
            broadcaster = load_user(stats["broadcast"]["author"], active=False)

            broadcaster.banned = 1
            broadcaster.ban_message = stats["broadcast"]["content"]

            reports = stuffimporter.itempaged_to_list(user_container.query_items("SELECT {'reason': u.report.reason, 'quote': u.report.quote} as user FROM Users u WHERE u.report.post_id = '" + stats['broadcast']['id'] + "'", enable_cross_partition_query=True))
            reason_effectives = {}
            for user_report in reports:
                report = user_report["user"]

                # Extract the most present reason from the dicts
                try:
                    reason_effectives[report["reason"]] += 1
                except KeyError:
                    reason_effectives[report["reason"]] = 1

            reason_effectives = sorted(reason_effectives.items(), key=lambda x: x[1])
            most_reason = reason_effectives[0][0]
            broadcaster.ban_reason = most_reason

            if most_reason != "offensive_name":
                reason_quotes = [user["quote"] for user in reports if user["reason"] == most_reason]
                results = {}
                for quote in reason_quotes:
                    results[quote] = 0
                    for secquote in reason_quotes:
                        if quote in secquote:
                            results[quote] += 1

                results = sorted(results.items(), key=lambda x: x[1])
                broadcaster.ban_most_quoted = results[0][0]
            else:
                broadcaster.ban_most_quoted = stats["broadcast"]["author_name"]

            broadcaster.uexport(user_container)

            with app.app_context(), babel_force_locale(broadcaster.lang):
                message = Mail(
                    from_email="random.broadcasting.selector@gmail.com",
                    to_emails=broadcaster.email,
                    subject=_("RandomBroadcastingSelector: You were banned."),
                    html_content=render_template("mails/banned.html", server_name=app.config["SERVER_NAME"], broadcaster=broadcaster)
                )
            send_mail(message)

            stats["users"]["num"] -= 1
            stats["users"]["banned"] += 1

            # Delete the banned user's message
            stats["broadcast"]["author_name"] = "[deleted]"
            stats["broadcast"]["content"] = "[deleted]"

            app.logger.info(f"Le diffuseur {broadcaster.get_id()} a été banni.")

        stuffimporter.set_stats(stats)

        return render_template("message.html", message=_("Your report has been saved."))

    rem_time = stuffimporter.seconds_to_str(get_rem_secs())

    return render_template("index.html", stats=stats, form=form, lang=get_lang(), rem_time=rem_time)

# All the login stuff


@app.route("/login/")
def login():
    return render_template("login.html")


@app.route("/login/google/")
def google_login():
    # Google Oauth Config
    oauth.register(
        name='google',
        client_id=config["google"]["oauth_id"],
        client_secret=config["google"]["oauth_secret"],
        server_metadata_url=config["google"]["discovery_url"],
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    # Redirect to google_login_callback function
    redirect_uri = url_for("google_login_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/login/google/callback")
def google_login_callback():
    token = oauth.google.authorize_access_token()
    response_json = token["userinfo"]

    if not response_json.get("email_verified"):
        return _("User email not available or not verified by %(service)s.", service="Google"), 400

    unique_id = "ggl_" + response_json["sub"]
    users_name = response_json["name"]
    users_email = response_json["email"]
    lang = response_json.get("locale")

    return login_or_create_user(unique_id, users_name, users_email, lang)


@app.route('/login/twitter/')
def twitter_login():
    # Twitter Oauth Config
    oauth.register(
        name='twitter',
        client_id=config["twitter"]["apiv1_key"],
        client_secret=config["twitter"]["apiv1_secret"],
        api_base_url='https://api.twitter.com/1.1/',
        request_token_url='https://api.twitter.com/oauth/request_token',
        access_token_url='https://api.twitter.com/oauth/access_token',
        authorize_url='https://api.twitter.com/oauth/authorize'
    )
    redirect_uri = url_for('twitter_login_callback', _external=True)
    return oauth.twitter.authorize_redirect(redirect_uri)


@app.route('/login/twitter/callback')
def twitter_login_callback():
    if request.args.get("denied"):
        lang = get_lang()
        return render_template("message.html", message=_("You cancelled the Continue with %(service)s action.", service="Twitter"))

    token = oauth.twitter.authorize_access_token()
    response = oauth.twitter.get("account/verify_credentials.json", params={"include_email": "true", "skip_status": "true"})
    response_json = response.json()

    unique_id = "twttr_" + response_json["id_str"]
    users_name = response_json["name"]
    users_email = response_json.get("email")
    if not users_email:
        return _("User email not available or not verified by %(service)s.", service="Twitter"), 400

    settings_response = oauth.twitter.get("account/settings.json")
    settings_response_json = settings_response.json()
    lang = settings_response_json.get("language")

    return login_or_create_user(unique_id, users_name, users_email, lang)


@app.route('/login/github/')
def github_login():
    # Github Oauth Config
    oauth.register(
        name='github',
        client_id=config["github"]["client_id"],
        client_secret=config["github"]["client_secret"],
        api_base_url='https://api.github.com/',
        access_token_url='https://github.com/login/oauth/access_token',
        authorize_url='https://github.com/login/oauth/authorize',
        userinfo_endpoint="https://api.github.com/user",
        client_kwargs={'scope': 'user:email'}
    )
    redirect_uri = url_for('github_login_callback', _external=True)
    return oauth.github.authorize_redirect(redirect_uri)


@app.route('/login/github/callback')
def github_login_callback():
    token = oauth.github.authorize_access_token()
    response = oauth.github.get("user")
    response_json = response.json()

    if not response_json.get('email'):
        emails_response = oauth.github.get('user/emails')
        emails_json = emails_response.json()
        response_json["email"] = [email['email'] for email in emails_json if email['primary']][0]

    unique_id = "gthb_" + str(response_json["id"])
    users_name = response_json["name"]
    users_email = response_json["email"]
    lang = None

    return login_or_create_user(unique_id, users_name, users_email, lang)


@app.route("/login/discord/")
def discord_login():
    # Discord Oauth Config
    oauth.register(
        name='discord',
        client_id=config["discord"]["client_id"],
        client_secret=config["discord"]["client_secret"],
        api_base_url='https://discordapp.com/api/',
        access_token_url='https://discordapp.com/api/oauth2/token',
        authorize_url='https://discordapp.com/api/oauth2/authorize',
        client_kwargs={
            'scope': 'identify email'
        }
    )

    # Redirect to discord_login_callback function
    redirect_uri = url_for("discord_login_callback", _external=True)
    return oauth.discord.authorize_redirect(redirect_uri)


@app.route("/login/discord/callback")
def discord_login_callback():
    if request.args.get("error") == "access_denied":
        lang = get_lang()
        return render_template("message.html", message=_("You cancelled the Continue with %(service)s action.", service="Discord"))

    token = oauth.discord.authorize_access_token()
    response = oauth.discord.get("users/@me")
    response_json = response.json()

    if not response_json.get("verified"):
        return _("User email not available or not verified by %(service)s.", service="Discord"), 400

    unique_id = "dscrd_" + response_json["id"]
    users_name = response_json["username"]
    users_email = response_json["email"]
    lang = response_json.get("locale")

    return login_or_create_user(unique_id, users_name, users_email, lang)


"""
@app.route('/login/twitch/')
def twitch_login():
	# Twitch Oauth Config
	oauth.register(
		name='twitch',
		client_id=config["twitch"]["client_id"],
		client_secret=config["twitch"]["client_secret"],
		api_base_url='https://api.twitch.tv/helix/',
		access_token_url='https://id.twitch.tv/oauth2/token',
		authorize_url='https://id.twitch.tv/oauth2/authorize',
        client_kwargs={
            'scope': 'user:read:email'
        }
	)
	redirect_uri = url_for('twitch_login_callback', _external=True)
	return oauth.twitch.authorize_redirect(redirect_uri)

@app.route('/login/twitch/callback')
def twitch_login_callback():
    if request.args.get("denied"):
        lang = get_lang()
        return render_template("message.html", message=_("You cancelled the Continue with %(service)s action.", service="Twitch"))

    token = oauth.twitch.authorize_access_token()
    response = oauth.twitch.get("users")
    response_json = response.json()
    return response_json

    unique_id = "twtch_" + response_json["id"]
    users_name = response_json["display_name"]
    users_email = response_json.get("email")
    if not users_email:
        return _("User email not available or not verified by %(service)s.", service="Twitch"), 400

    lang = ""

    return login_or_create_user(unique_id, users_name, users_email, lang)

@app.route('/login/facebook/')
def facebook_login():
	# Facebook Oauth Config
	oauth.register(
		name='facebook',
		client_id=config["facebook"]["client_id"],
		client_secret=config["facebook"]["client_secret"],
		api_base_url='https://graph.facebook.com/',
		access_token_url='https://graph.facebook.com/oauth/access_token',
		authorize_url='https://www.facebook.com/dialog/oauth',
		client_kwargs={'scope': 'email public_profile'},
        userinfo_endpoint="https://graph.facebook.com/me?fields=id,name,email,languages"
	)
	redirect_uri = url_for('facebook_login_callback', _external=True)
	return oauth.facebook.authorize_redirect(redirect_uri)

@app.route('/login/facebook/callback')
def facebook_login_callback():
	token = oauth.facebook.authorize_access_token()
	profile = token["userinfo"]

	return profile
	return redirect(url_for("index", lang=session.get("lang")))
"""


@app.route("/logout/")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

# General stuff


@app.route("/history/")
def history_redirect():
    num = math.ceil((int(stats["broadcast"]["id"])) / 5)
    return redirect(url_for("history", page=num))


@app.route("/history/<int:page>")
def history(page):
    query_list = [f"p.id = '{post_id}'" for post_id in range((5 * page) - 4, (5 * page) + 1)]
    query_str = " OR ".join(query_list)

    try:
        query_result = post_container.query_items(f"SELECT * FROM Posts p WHERE {query_str}", enable_cross_partition_query=True)
        post_list = stuffimporter.itempaged_to_list(query_result)
    except StopIteration:
        post_list = []

    return render_template("history.html", post_list=reversed(post_list), hist_page=int(page))


@app.route("/post/")
def specific_post_search():
    max_id = int(stats["broadcast"]["id"]) - int(bool(stats["broadcast"]["content"]))
    return render_template("post_search.html", max_post_id=max_id)


@app.route("/post/<int:id>")
def specific_post(id):
    try:
        post = post_container.query_items(f"SELECT * FROM Posts p WHERE p.id = '{id}'", enable_cross_partition_query=True).next()
    except StopIteration:
        abort(404)

    return render_template("post.html", post=post)


@app.route("/statistics/")
def statistics():
    if stats["time"]["stats_last_edited"] + 600 < time.time():
        stats["users"]["seen_msg"] = user_container.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {stats['broadcast']['_ts']}", enable_cross_partition_query=True).next()
        stats["users"]["last_active"]["1h"] = user_container.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 3600}", enable_cross_partition_query=True).next()
        stats["users"]["last_active"]["24h"] = user_container.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 86400}", enable_cross_partition_query=True).next()
        stats["users"]["last_active"]["week"] = user_container.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 604800}", enable_cross_partition_query=True).next()

        stats["top_posts"]["5_most_upped"] = stuffimporter.itempaged_to_list(post_container.query_items("SELECT * FROM Posts p ORDER BY p.upvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_downed"] = stuffimporter.itempaged_to_list(post_container.query_items("SELECT * FROM Posts p ORDER BY p.downvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_pop"] = stuffimporter.itempaged_to_list(post_container.query_items("SELECT * FROM Posts p ORDER BY p.ratio DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_unpop"] = stuffimporter.itempaged_to_list(post_container.query_items("SELECT * FROM Posts p ORDER BY p.ratio ASC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))

        stats["time"]["stats_last_edited"] = time.time()

        stuffimporter.set_stats(stats)

        app.logger.debug("Les stats ont étés mis à jour")

    uptime_str = stuffimporter.seconds_to_str(time.time() - stats["time"]["start_time"])
    rem_time = stuffimporter.seconds_to_str(get_rem_secs())

    return render_template("stats.html", stats=stats, uptime_str=uptime_str, rem_time=rem_time, lang=get_lang())


@app.route("/broadcast/", methods=["GET", "POST"])
@login_required
@role_required("broadcaster")
def broadcast():
    if stats["broadcast"]["content"]:
        return render_template("message.html", message=_("You have already made your broadcast."))

    form = BroadcastForm()

    if form.validate_on_submit():
        stats["broadcast"]["id"] = str(int(stats["broadcast"]["id"]) + 1)
        stats["broadcast"]["content"] = form.message.data
        stats["broadcast"]["author"] = stats["roles"]["broadcaster"][0]
        stats["broadcast"]["author_name"] = form.display_name.data
        stats["broadcast"]["_ts"] = time.time()

        test = translator.translate_text(form.message.data, target_lang="EN-US")
        stats["broadcast"]["lang"] = test.detected_source_lang.split("-")[0].lower()

        for language in translator.get_target_languages():
            lang_code = language.code.split("-")[0]
            stats["broadcast"]["trads"][lang_code.lower()] = translator.translate_text(form.message.data, target_lang=language.code).text

        stats["broadcast"]["_ts"] = time.time()

        stuffimporter.set_stats(stats)

        app.logger.info("La diffusion a été enregistrée.")
        return render_template("message.html", message=_("Your broadcast has been saved, you can now share this website to everyone you know so that everyone sees your message."))

    return render_template("broadcast.html", form=form, stats=stats)


@app.route("/ban-appeal/", methods=["GET", "POST"])
def ban_appeal():
    banned_id = request.args.get("user_id")
    if banned_id not in stats["roles"]["ban_appealers"].keys():
        return render_template("message.html", message=_("You have to be banned to have access to this page."))
    elif stats["roles"]["ban_appealers"][banned_id] != request.args.get("appeal_code"):
        app.logger.info(f"{request.args.get['user_id']} a essayé de faire la malin en changeant le html des hidden inputs sur la page de demande de débannissement.")
        return render_template("message.html", message=_("Hey smartass, quit trying."))

    form = BanAppealForm()

    if form.validate_on_submit():
        user = load_user(form.user_id.data, active=False)
        if user.ban_appeal:
            app.logger.info(f"{form.user_id.data} a essayé de faire une demande de débannissement alors qu'il en a déjà fait une.")
            return render_template("message.html", message=_("You have already made a ban appeal."))

        user.ban_appeal = form.reason.data
        user.uexport(user_container)

        stats["roles"]["ban_appealers"].pop(banned_id)
        stuffimporter.set_stats(stats)

        requests.get(config["telegram_send_url"] + "ban+appeal+received")
        app.logger.info("Une demande de débannissment a été enregistrée.")
        return render_template("message.html", message=_("Your ban appeal has been saved, it will be reviewed shortly."))

    return render_template("banned.html", form=form, user_id=banned_id)


@app.route("/about/")
def about():
    return render_template("about.html")


@app.route("/reselect/", methods=["GET", "POST"])
@login_required
@role_required("preselecteds")
def reselect():
    opti_next_sel = time.time() + (brod_change_threshold * len(stats["roles"]["futur_broadcasters"])) + get_rem_secs()
    pessi_next_sel = time.time() + (brod_change_threshold * 1.99 * len(stats["roles"]["futur_broadcasters"])) + get_rem_secs()
    if not stats["broadcast"]["content"]:
        pessi_next_sel += brod_change_threshold

    opti_date_str = format_datetime(datetime.datetime.utcfromtimestamp(opti_next_sel), format="long")
    pessi_date_str = format_datetime(datetime.datetime.utcfromtimestamp(pessi_next_sel), format="long")

    if opti_date_str == pessi_date_str:
        interval_to_watch_out = _("the %(date)s", date=opti_date_str)
    else:
        interval_to_watch_out = _("between the %(opti)s and the %(pessi)s", opti=opti_date_str, pessi=pessi_date_str)

    if request.method == "POST":
        user_id = current_user.get_id()
        if request.form.get("yes"):
            stats["roles"]["futur_broadcasters"].append(user_id)
            done_message = _("You have been reselected successfully. Watch your inbox %(time_interval)s.", time_interval=interval_to_watch_out)
        else:
            done_message = _("You have been successfully removed from the preselected list.")

        stats["roles"]["preselecteds"].pop(user_id)
        stuffimporter.set_stats(stats)

        return render_template("message.html", message=done_message)

    return render_template("reselect.html", time_interval=interval_to_watch_out)


@app.route("/parameters/", methods=["GET", "POST"])
@login_required
def parameters():
    if request.method == "POST":
        if request.form.get("del_acc"):
            u_id = current_user.get_id()
            user_container.delete_item(u_id, u_id)
            logout_user()

            stats["users"]["num"] -= 1
            stuffimporter.set_stats(stats)

            end_msg = _("Deleted account successfully.")

        return render_template("message.html", message=end_msg)

    return render_template("parameters.html")

# Callbacks


@app.route("/vote/", methods=["POST"])
@login_required
def vote_callback():
    if not stats["broadcast"]["content"]:
        return render_template("message.html", message=_("No post is live right now so you can't vote."))

    if request.form["action"] == "upvote":
        if current_user.upvote == stats["broadcast"]["id"]:
            current_user.upvote = ""
            stats["broadcast"]["upvotes"] -= 1
        else:
            current_user.upvote = stats["broadcast"]["id"]
            stats["broadcast"]["upvotes"] += 1
            if current_user.downvote == stats["broadcast"]["id"]:
                current_user.downvote = ""
                stats["broadcast"]["downvotes"] -= 1
    elif request.form["action"] == "downvote":
        if current_user.downvote == stats["broadcast"]["id"]:
            current_user.downvote = ""
            stats["broadcast"]["downvotes"] -= 1
        else:
            current_user.downvote = stats["broadcast"]["id"]
            stats["broadcast"]["downvotes"] += 1
            if current_user.upvote == stats["broadcast"]["id"]:
                current_user.upvote = ""
                stats["broadcast"]["upvotes"] -= 1

    current_user.uexport(user_container)
    stuffimporter.set_stats(stats)

    return request.form["action"]

# Custom validators


class MinWords(object):
    def __init__(self, minimum=-1, message=None):
        self.minimum = minimum
        if not message:
            message = lazy_ngettext('Field must have at least %(minimum)s word.', 'Field must have at least %(minimum)s words.', minimum=minimum)
        self.message = message

    def __call__(self, form, field):
        words = field.data and len(re.findall(r"[\w']+", field.data)) or 0
        if words < self.minimum:
            raise validators.ValidationError(self.message)


class InString(object):
    def __init__(self, string="", message=None):
        self.string = string
        if not message:
            message = lazy_gettext('Field must be included in "%(string)s".', string=string)
        self.message = message

    def __call__(self, form, field):
        if field.data not in self.string and form.reason.data != "offensive_name":
            raise validators.ValidationError(self.message)


class StopIfBlah(object):
    def __init__(self, message=None):
        if not message:
            message = 'blah.'
        self.message = message

    def __call__(self, form, field):
        if form.reason.data == "offensive_name":
            raise validators.StopValidation

# WTForms


class BroadcastForm(FlaskForm):
    message = TextAreaField(lazy_gettext("Enter the message you want to send to this website's users."), validators=[
        validators.InputRequired(),
        validators.Length(0, 512),
        MinWords(2, message=lazy_gettext("I'm sorry but you are going to have to write more than one word."))
    ])

    display_name = StringField(lazy_gettext("Author of this message (name that you want to be designated as that everyone will see.):"), validators=[
        validators.InputRequired(),
        validators.Length(0, 64)
    ])

    submit = SubmitField(lazy_gettext("Submit"))


class BanAppealForm(FlaskForm):
    user_id = HiddenField(validators=[
        validators.InputRequired(),
        validators.AnyOf(stats["roles"]["ban_appealers"].keys(), message=lazy_gettext("You have to be banned to submit this form."))
    ])

    reason = TextAreaField("Enter why you should be unbanned.", validators=[
        validators.InputRequired(),
        validators.Length(0, 512),
        MinWords(2, message=lazy_gettext("If you really want to get unbanned you should write a bit more than that (more than one word)."))
    ])

    submit = SubmitField(lazy_gettext("Submit"))


class ReportForm(FlaskForm):
    reason = RadioField(choices=[
        ("harassement", lazy_gettext("Is this broadcast harassing, insulting or encouraging hate against anyone ?")),
        ("mild_language", lazy_gettext("Is this broadcast using too much mild language for a family friendly website ?")),
        ("link", lazy_gettext('Does this broadcast contain any link (like "http://example.com") or pseudo link (like "example.com") or attempts at putting a link that doesn\'t look like one (like "e x a m p l e . c o m" or "example dot com") ?')),
        ("offensive_name", lazy_gettext("Has this broadcasts author chosen an offending name ?"))
    ], validators=[
        validators.InputRequired(),
    ])

    message_quote = StringField(validators=[
        StopIfBlah(),
        validators.InputRequired(),
        InString(stats["broadcast"]["content"], message=lazy_gettext("The quote you supplied isn't in the broadcast.")),
        MinWords(2, message=lazy_gettext("The quote you supplied has only got one word when it has to have at least two."))
    ])

    submit = SubmitField(lazy_gettext("Submit"))


class BanUnbanForm(FlaskForm):
    user_id = StringField("Id de la personne concernée : ", validators=[
        validators.InputRequired()
    ])

    banunban = RadioField(choices=[
        ("ban", "Bannir"),
        ("déban", "Débannir")
    ], validators=[
        validators.InputRequired(),
    ])

    ban_message = StringField("user_to_ban.ban_message : ", validators=[
        validators.Optional()
    ])

    ban_reason = StringField("user_to_ban.ban_reason : ", validators=[
        validators.Optional()
    ])

    ban_most_quoted = StringField("user_to_ban.ban_most_quoted : ", validators=[
        validators.Optional()
    ])

    silenced = BooleanField("Silencieux")

    submit = SubmitField()


class AppealViewForm(FlaskForm):
    user_id = HiddenField()

    whatodo = RadioField(choices=[
        ("accepté", "Accepter"),
        ("refusé", "Refuser")
    ], validators=[
        validators.InputRequired(),
    ])

    silenced = BooleanField("Silencieux")

    submit = SubmitField()

# Legal stuff


@app.route("/privacy-policy/")
def privacy_policy():
    return render_template("privacy_policy.html")


@app.route("/terms-of-service/")
def terms_of_service():
    return render_template("terms_of_service.html")


@app.route("/sitemap/")
def sitemap():
    return render_template("sitemap.html")

# Crawling control


@app.route("/robots.txt")
def robots():
    return "User-agent: *<br>Disallow:<br>Allow: /<br>Sitemap: /sitemap"

# Health check


@app.route("/ping/")
def ping():
    return _("App online"), 200

# Admin


@app.route("/super-secret-admin-panel/", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_panel():
    global stats
    identifier = current_user.get_id() if current_user.is_authenticated else request.remote_addr

    try:
        banned_user = user_container.query_items("SELECT * FROM Users u WHERE IS_DEFINED(u.ban) AND u.ban.appeal <> '' OFFSET 0 LIMIT 1", enable_cross_partition_query=True).next()
    except StopIteration:
        banned_user = anon_user_getter()
        banned_user.id_ = "no_ban_appeal"

    banunban = BanUnbanForm()
    appealview = AppealViewForm()

    if request.method == "POST":
        if banunban.submit.data and banunban.verify():
            user = load_user(banunban.user_id.data, active=False)
            if banunban.banunban.data == "ban":
                if user.is_broadcaster:
                    # Delete the banned user's message
                    stats["broadcast"]["author_name"] = "[deleted]"
                    stats["broadcast"]["content"] = "[deleted]"

                user.banned = 1
                user.ban_message = banunban.ban_message.data
                user.ban_reason = banunban.ban_reason.data
                user.ban_most_quoted = banunban.ban_most_quoted.data

                if not banunban.slienced.data:
                    with app.app_context(), babel_force_locale(user.lang):
                        message = Mail(
                            from_email="random.broadcasting.selector@gmail.com",
                            to_emails=user.email,
                            subject=_("RandomBroadcastingSelector: You were banned."),
                            html_content=render_template("mails/banned.html", server_name=app.config["SERVER_NAME"], user=user)
                        )
                    send_mail(message)

                stats["users"]["num"] -= 1
                stats["users"]["banned"] += 1

                app.logger.info(f"{identifier} a banni {user.get_id()} avec succès.")
            else:
                user = load_user(banunban.user_id.data, active=False)
                user.banned = 0

                if not banunban.slienced.data:
                    with app.app_context(), babel_force_locale(user.lang):
                        message = Mail(
                            from_email="random.broadcasting.selector@gmail.com",
                            to_emails=user.email,
                            subject=_("RandomBroadcastingSelector: You are no longer banned."),
                            html_content=render_template("mails/unbanned.html", server_name=app.config["SERVER_NAME"])
                        )
                    send_mail(message)

                stats["users"]["num"] += 1
                stats["users"]["banned"] -= 1

                app.logger.info(f"{identifier} a débanni {user.get_id()} avec succès.")

            user.uexport(user_container)
            stuffimporter.set_stats(stats)

        elif appealview.submit.data and appealview.verify():
            user = load_user(appealview.user_id.data, active=False)
            if appealview.whatodo.data == "accepté":
                user.banned = 0

                if not appealview.slienced.data:
                    with app.app_context(), babel_force_locale(user.lang):
                        message = Mail(
                            from_email="random.broadcasting.selector@gmail.com",
                            to_emails=user.email,
                            subject=_("RandomBroadcastingSelector: You are no longer banned."),
                            html_content=render_template("mails/unbanned.html", server_name=app.config["SERVER_NAME"])
                        )
                    send_mail(message)

                stats["users"]["num"] += 1
                stats["users"]["banned"] -= 1

                stuffimporter.set_stats(stats)
                app.logger.info(f"{identifier} a accepté la demande de débannissement de {user.get_id()} avec succès.")
            else:
                user = load_user(appealview.user_id.data, active=False)
                user.ban_appeal = ""

                if not appealview.slienced.data:
                    with app.app_context(), babel_force_locale(user.lang):
                        message = Mail(
                            from_email="random.broadcasting.selector@gmail.com",
                            to_emails=user.email,
                            subject=_("RandomBroadcastingSelector: Your ban appeal was refused."),
                            html_content=render_template("mails/refused.html", server_name=app.config["SERVER_NAME"])
                        )
                    send_mail(message)

            user.uexport()

        elif request.form["action"] == "import_stats":
            filename = list(request.files.to_dict().keys())[0]
            stats = json.load(request.files[filename].stream)
            stuffimporter.set_stats(stats)
        elif request.form["action"] == "export_stats":
            return pprint.pformat(stats, indent=4, sort_dicts=False).replace("\n", "<br>").replace("    ", "&emsp;")
        elif request.form["action"] == "import_logs":
            filename = list(request.files.to_dict().keys())[0]
            with open("./logs.log", "wb") as logs_file:
                logs_file.write(request.files[filename].stream.read())
            request.files[filename].stream.close()
        elif request.form["action"] == "export_logs":
            with open("./logs.log") as logs_f:
                return logs_f.read().replace("\n", "<br>")

        return render_template("message.html", message="Succès de l'action " + request.form["action"])

    stuffimporter.set_stats(stats)

    app.logger.info(f"{identifier} a accédé au panneau d'administration avec succès.")
    return render_template("admin_panel.html", banunban=banunban, appealview=appealview, banned_user=banned_user)

# Error handling


@app.errorhandler(401)
def unauthorized(e):
    return render_template(
        "error.html",
        err_title="401 Unauthorized",
        err_img_src="/static/img/you shall not pass.gif",
        err_img_alt="Gandalf you shall not pass GIF",
        err_msg=e
    ), 401


@app.errorhandler(403)
def forbidden(e):
    return render_template(
        "error.html",
        err_title="403 Forbidden",
        err_img_src="/static/img/you shall not pass.gif",
        err_img_alt="Gandalf you shall not pass GIF",
        err_msg=e
    ), 403


@app.errorhandler(404)
def not_found(e):
    return render_template(
        "error.html",
        err_title="404 Not Found",
        err_img_src="/static/img/confused travolta.gif",
        err_img_alt="Confused Travolta GIF",
        err_msg=e
    ), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template(
        "error.html",
        err_title="500 Internal Server Error",
        err_img_src="/static/img/this is fine.gif",
        err_img_alt="This is fine dog GIF",
        err_msg=e
    ), 500

# CSP reports handling


@app.route('/report-csp-violations', methods=['POST'])
def report():
    content = request.get_json(force=True)
    app.logger.warning("CSP violation occurred")
    requests.get(config["telegram_send_url"] + "csp+violation+occured")

    message = Mail(
        from_email="random.broadcasting.selector@gmail.com",
        to_emails="pub@elfin.fr",
        subject="RandomBroadcastingSelector : CSP violation.",
        html_content=json.dumps(content, indent=4, sort_keys=True)
    )
    send_mail(message)
    return "", 204


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=testing)  # ne pas changer 0.0.0.0 pour la véritable adresse pasque ça marche pas
