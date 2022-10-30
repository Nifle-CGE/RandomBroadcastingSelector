# Python standard libraries
import datetime
import secrets
import json
import os
import time
import random
import copy
import math
import re
import logging

# Third-party libraries
from flask import Flask, redirect, render_template, url_for, session, request, abort, send_file

from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from flask_wtf import FlaskForm
from wtforms.fields import StringField, TextAreaField, HiddenField, RadioField, SubmitField, BooleanField
from wtforms import validators

from flask_babel import Babel, format_date, format_number, _, ngettext, lazy_gettext, lazy_ngettext, force_locale as babel_force_locale

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
brod_change_threshold = 86400
if testing:
    from tests.ip_getter import get_ip
    app.config["SERVER_NAME"] = get_ip() + ":5000"
    
    app.logger.level = logging.DEBUG
    app.logger.debug("Mode test activé.")
else:
    app.config["SERVER_NAME"] = "rbs.azurewebsites.net"


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

# Config setup
config = _stuffimporter.StuffImporter.get_config()

# Deepl translation setup
translator = deepl.Translator(config["deepl_auth_key"])

LANGUAGE_CODES = [lang.code.lower() for lang in translator.get_source_languages()]
SUPPORTED_LANGUAGES = ["en", "fr"]
app.logger.debug("Traducteur mis en place.")

# Internationalization setup
babel = Babel(app)

# Database setup
cc = CosmosClient(config["db"]["url"], config["db"]["key"])
db = cc.get_database_client("Main Database")
u_cont = db.get_container_client("Web RBS Users")
p_cont = db.get_container_client("Web RBS Posts")
app.logger.debug("Base de donnée mise en place.")

stuffimporter = _stuffimporter.StuffImporter(u_cont, _, ngettext)

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
    "default-src": "none",
    "object-src": "none",
    "script-src": "'self'",
    "style-src": "'self'",
    "media-src": "'self'",
    "frame-src": "'self'",
    "base-uri": "'self'",
    "connect-src": "'self'",
    "font-src": [
        "'self'",
        "data:"
    ],
    "img-src": [
        "'self'",
        "img.shields.io"
    ]
} # TODO : mettre report-uri
talisman = Talisman(
    app,
    content_security_policy=csp,
    content_security_policy_nonce_in=[
        'script-src',
        "style-src"
    ]
)

app.logger.info("Application lancée.")

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id, active=True):
    user = User()
    if not user.uimport(u_cont, user_id):
        return None

    if user.id_ == stats["broadcast"]["author"]:
        user.is_broadcaster = True

    if active:
        user.last_active = time.time()
        user.uexport(u_cont)

    return user

# Babel stuff
@babel.localeselector
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

# Useful defs
def send_mail(mail):
    if not testing:
        sg_client.send(mail)
    else:
        print(f"Mail envoyé avec le sujet \"{mail.subject}\"")

@app.before_request
def verify_broadcast():
    if testing: return
    skip_save = False
    if stats["broadcast"]["content"] == "[deleted]" and stats["broadcast"]["author_name"] == "[deleted]":
        skip_save = True
    else:
        if not stats["broadcast"]["content"]:
            if stats["time"]["last_broadcaster"] + brod_change_threshold > time.time():
                end_msg = ""
                if not stats["broadcast"]["warning"]["12h"] and stats["time"]["last_broadcaster"] + 43200 < time.time():
                    brod = load_user(stats["broadcast"]["author"], active=False)
                
                    with app.app_context(), babel_force_locale(brod.lang):
                        message = Mail(
                            from_email="random.broadcasting.selector@gmail.com",
                            to_emails=brod.email,
                            subject=_("RandomBroadcastingSelector: Just a reminder that you are the one."),
                            html_content=render_template("mails/reminder.html", server_name=app.config["SERVER_NAME"], brod_code=stats["codes"]["broadcast"], rem_hours=12)
                        )
                    send_mail(message)

                    stats["broadcast"]["warning"]["12h"] = 1
                    stuffimporter.set_stats(stats)

                    end_msg = ", rappel des 12h envoyé"
                elif not stats["broadcast"]["warning"]["1h"] and stats["time"]["last_broadcaster"] + 82800 < time.time():
                    brod = load_user(stats["broadcast"]["author"], active=False)
                
                    with app.app_context(), babel_force_locale(brod.lang):
                        message = Mail(
                            from_email="random.broadcasting.selector@gmail.com",
                            to_emails=brod.email,
                            subject=_("RandomBroadcastingSelector: Just a reminder that you are the one."),
                            html_content=render_template("mails/reminder.html", server_name=app.config["SERVER_NAME"], brod_code=stats["codes"]["broadcast"], rem_hours=1)
                        )
                    send_mail(message)

                    stats["broadcast"]["warning"]["1h"] = 1
                    stuffimporter.set_stats(stats)
                    
                    end_msg = ", rappel des 1h envoyé"

                app.logger.debug(f"Le diffuseur a toujours le temps pour faire sa diffusion{end_msg}.")
                return
            else:
                skip_save = True
        elif stats["time"]["last_broadcast"] + brod_change_threshold > time.time():
            app.logger.debug("Le post a toujours le temps d'être évalué.")
            return

    if not skip_save:
        # Save current post
        with open("samples/sample_post.json", "r", encoding="utf-8") as sample_file:
            new_post = json.load(sample_file)

        new_post["id"] = stats["broadcast"]["id"]
        new_post["content"] = stats["broadcast"]["content"]
        new_post["author"] = stats["broadcast"]["author"]
        new_post["author_name"] = stats["broadcast"]["author_name"]
        new_post["date"] = stats["broadcast"]["date"]
        new_post["lang"] = stats["broadcast"]["lang"]
        new_post["upvotes"] = stats["broadcast"]["upvotes"]
        new_post["downvotes"] = stats["broadcast"]["downvotes"]
        try:
            new_post["ratio"] = new_post["upvotes"] / new_post["downvotes"]
        except ZeroDivisionError:
            new_post["ratio"] = new_post["upvotes"]
        p_cont.create_item(new_post)

        # Update stats in relation of the current post
        stats["broadcasts"]["msgs_sent"] += 1
        try:
            stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] += 1
        except KeyError:
            stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] = 1

        stats["broadcasts"]["words_sent"] += len(re.findall(r"[\w']+", new_post["content"])) # add number of words
        stats["broadcasts"]["characters_sent"] += len(new_post["content"]) # add number of chars
    
    # Select another broadcaster
    if stats["broadcast"]["futur"]["broadcasters"]:
        stats["broadcast"]["author"] = stats["broadcast"]["futur"]["broadcasters"].pop(0)
    else:
        stats["broadcast"]["author"] = random.choice(stuffimporter.pot_brods(stats["broadcast"]["author"]))
    stats["broadcast"]["author_name"] = ""
    stats["broadcast"]["content"] = ""
    stats["broadcast"]["date"] = ""
    stats["broadcast"]["upvotes"] = 0
    stats["broadcast"]["downvotes"] = 0
    stats["broadcast"]["reports"] = 0
    stats["broadcast"]["warning"]["12h"] = 0
    stats["broadcast"]["warning"]["1h"] = 0

    stats["time"]["last_broadcaster"] = time.time()

    code = secrets.token_urlsafe(32)
    stats["codes"]["broadcast"] = code

    brod = load_user(stats["broadcast"]["author"], active=False)
    
    # Send mail to the new broadcaster
    with app.app_context(), babel_force_locale(brod.lang):
        message = Mail(
            from_email="random.broadcasting.selector@gmail.com",
            to_emails=brod.email,
            subject=_("RandomBroadcastingSelector: You are the one."),
            html_content=render_template("mails/broadcaster.html", server_name=app.config["SERVER_NAME"], brod_code=code)
        )
    send_mail(message)

    stuffimporter.set_stats(stats)

    app.logger.info(f"Nouveau diffuseur {brod.id_} a été sélectionné.")
    return

def login_or_create_user(id_:str, name:str, email:str, lang:str):
    if lang not in LANGUAGE_CODES:
        lang = "en"

    # Test to see if the user exists in the db
    user = load_user(id_)

    # Doesn't exist? Add it to the database.
    if not user:
        try:
            fraud_id = u_cont.query_items(f"SELECT u.id FROM Users u WHERE u.email = '{email}'", enable_cross_partition_query=True).next()
            app.logger.info(f"Double compte de {fraud_id} empéché.")
            return render_template("message.html", message=_("Double accounts aren't allowed."))
        except StopIteration:
            pass

        new_user = User(id_=id_, name=name, email=email, lang=lang)
        new_user.last_active = time.time()
        new_user.uexport(u_cont)

        stats["users"]["num"] += 1
        stuffimporter.set_stats(stats)

        user = new_user

        app.logger.info(f"L'utilisateur {user.id_} a été créé.")
    if user.banned: # if user banned send the ban appeal form
        code = secrets.token_urlsafe(32)
        stats["codes"]["ban_appeal"][user.id_] = code
        stuffimporter.set_stats(stats)

        return redirect(url_for("ban_appeal", user_id=user.id_, appeal_code=code))

    # Begin user session by logging the user in
    user.is_authenticated = True
    login_user(user)

    # Send user back to homepage
    return redirect(url_for("index"))

# Routing
@app.route("/", methods=["GET", "POST"])
def index():
    form = ReportForm()
    
    if form.validate_on_submit(): # Report callback
        if not stats["broadcast"]["content"]:
            app.logger.warning(f"{current_user.id_} a essayé de signaler un post alors qu'il n'y en a pas.")
            return render_template("message.html", message=_("No post is live right now so you can't report one."))
        elif current_user.report_post_id == stats["broadcast"]["id"]:
            app.logger.debug(f"{current_user.id_} a essayé de resignaler le post.")
            return render_template("message.html", message=_("You have already reported this post so you can't report it again."))

        current_user.report_post_id = stats["broadcast"]["id"]
        current_user.report_reason = form.reason.data
        current_user.report_quote = form.message_quote.data

        current_user.uexport(u_cont)

        stats["broadcast"]["reports"] += 1

        if stats["users"]["seen_msg"] > (3 * math.sqrt(stats["users"]["num"])) and stats["broadcast"]["reports"] > (stats["users"]["seen_msg"] / 2):
            brod = load_user(stats["broadcast"]["author"], active=False)

            brod.banned = 1
            brod.ban_message = stats["broadcast"]["content"]

            reports = stuffimporter.itempaged_to_list(u_cont.query_items("SELECT {'reason': u.report.reason, 'quote': u.report.quote} as user FROM Users u WHERE u.report.post_id = '" + stats['broadcast']['id'] + "'", enable_cross_partition_query=True))
            reason_effectives = {}
            for user_report in reports:
                report = user_report["user"]

                # Extract the most present reason from the dicts
                try:
                    reason_effectives[report["reason"]] += 1
                except KeyError:
                    reason_effectives[report["reason"]] = 1

            reason_effectives = sorted(reason_effectives.items(), key=lambda x:x[1])
            most_reason = reason_effectives[0][0]
            brod.ban_reason = most_reason

            if most_reason != "offensive_name":
                reason_quotes = [user["quote"] for user in reports if user["reason"] == most_reason]
                results = {}
                for quote in reason_quotes:
                    results[quote] = 0
                    for secquote in reason_quotes:
                        if quote in secquote:
                            results[quote] += 1

                results = sorted(results.items(), key=lambda x:x[1])
                brod.ban_most_quoted = results[0][0]
            else:
                brod.ban_most_quoted = stats["broadcast"]["author_name"]

            brod.uexport(u_cont)

            with app.app_context(), babel_force_locale(brod.lang):
                message = Mail(
                    from_email="random.broadcasting.selector@gmail.com",
                    to_emails=brod.email,
                    subject=_("RandomBroadcastingSelector: You were banned."),
                    html_content=render_template("mails/banned.html", server_name=app.config["SERVER_NAME"], brod=brod)
                )
            send_mail(message)

            stats["users"]["num"] -= 1
            stats["users"]["banned"] += 1

            # Delete the banned user's message
            stats["broadcast"]["author_name"] = "[deleted]"
            stats["broadcast"]["content"] = "[deleted]"

            app.logger.info(f"Le diffuseur {brod.id_} a été banni.")

        stuffimporter.set_stats(stats)

        return render_template("message.html", message=_("Your report has been saved."))

    if stats["broadcast"]["content"]:
        rem_secs = stats["time"]["last_broadcast"] + brod_change_threshold - time.time()
    else:
        rem_secs = stats["time"]["last_broadcaster"] + brod_change_threshold - time.time()
    rem_time = stuffimporter.seconds_to_str(rem_secs)

    return render_template("index.html", stats=stats, form=form, lang=get_lang(), rem_time=rem_time, random=random)

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
    lang = response_json["locale"]
    if lang not in LANGUAGE_CODES:
        lang = request.accept_languages.best_match(LANGUAGE_CODES)

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
    if lang not in LANGUAGE_CODES:
        lang = request.accept_languages.best_match(LANGUAGE_CODES)

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
    lang = request.accept_languages.best_match(LANGUAGE_CODES)

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
    lang = response_json["locale"]
    if lang not in LANGUAGE_CODES:
        lang = request.accept_languages.best_match(LANGUAGE_CODES)

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

    lang = request.accept_languages.best_match(LANGUAGE_CODES)

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
    num = math.ceil((int(stats["broadcast"]["id"]) - 1) / 5)
    return redirect(url_for("history", page=num))

@app.route("/history/<int:page>")
def history(page):
    q_list = [f"p.id = '{post_id}'" for post_id in range((5 * page) - 4, (5 * page) + 1)]
    q_str = " OR ".join(q_list)

    try:
        q_result = p_cont.query_items(f"SELECT * FROM Posts p WHERE {q_str}", enable_cross_partition_query=True)
        post_list = stuffimporter.itempaged_to_list(q_result)
    except StopIteration:
        post_list = []
    
    return render_template("history.html", post_list=reversed(post_list), hist_page=int(page), random=random)

@app.route("/post/")
def specific_post_search():
    max_id = int(stats["broadcast"]["id"]) - int(bool(stats["broadcast"]["content"]))
    return render_template("post_search.html", max_post_id=max_id)

@app.route("/post/<int:id>")
def specific_post(id):
    try:
        post = p_cont.query_items(f"SELECT * FROM Posts p WHERE p.id = '{id}'", enable_cross_partition_query=True).next()
    except StopIteration:
        abort(404)

    return render_template("post.html", post=post, random=random)

@app.route("/statistics/")
def statistics():
    if stats["time"]["stats_last_edited"] + 600 < time.time():
        start_time = time.time()

        stats["users"]["seen_msg"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {stats['time']['last_broadcast']}", enable_cross_partition_query=True).next()
        stats["users"]["last_active"]["1h"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 3600}", enable_cross_partition_query=True).next()
        stats["users"]["last_active"]["24h"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 86400}", enable_cross_partition_query=True).next()
        stats["users"]["last_active"]["week"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 604800}", enable_cross_partition_query=True).next()
        
        stats["top_posts"]["5_most_upped"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.upvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_downed"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.downvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_pop"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_unpop"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio ASC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        
        stats["time"]["stats_last_edited"] = time.time()
        stats["time"]["stats_getting"] = time.time() - start_time

        app.logger.debug("Les stats ont étés mis a jour")

    stuffimporter.set_stats(stats)

    uptime_str = stuffimporter.seconds_to_str(time.time() - stats["time"]["start_time"])

    return render_template("stats.html", stats=stats, uptime_str=uptime_str, lang=get_lang(), random=random)

@app.route("/stats.json")
def stats_file():
    stats_file = copy.deepcopy(stats)
    stats_file.pop("codes")
    stats_file["broadcast"].pop("author")

    for i in stats["top_posts"]:
        for j in range(len(stats["top_posts"][i])):
            for k in stats["top_posts"][i][j]:
                if k.startswith("_") or k == "author":
                    stats_file["top_posts"][i][j].pop(k)

    app.logger.debug("Fichier stats exporté.")
    return stats_file

@app.route("/broadcast/", methods=["GET", "POST"])
@login_required
def broadcast():
    if current_user.id_ != stats["broadcast"]["author"]:
        return render_template("message.html", message=_("You have to be broadcaster to have access to this page."))
    elif stats["broadcast"]["content"]:
        return render_template("message.html", message=_("You have already made your broadcast."))

    form = BroadcastForm()
    
    if form.validate_on_submit():
        stats["codes"]["broadcast"] = ""

        stats["broadcast"]["id"] = str(int(stats["broadcast"]["id"]) + 1)
        stats["broadcast"]["content"] = form.message.data
        stats["broadcast"]["author_name"] = form.display_name.data
        stats["broadcast"]["date"] = str(datetime.datetime.today().date())
    
        test = translator.translate_text(form.message.data, target_lang="EN-US")
        stats["broadcast"]["lang"] = test.detected_source_lang.split("-")[0].lower()
    
        for language in translator.get_target_languages():
            lang_code = language.code.split("-")[0]
            stats["broadcast"]["trads"][lang_code.lower()] = translator.translate_text(form.message.data, target_lang=language.code).text
        
        stats["time"]["last_broadcast"] = time.time()
    
        stuffimporter.set_stats(stats)
    
        app.logger.info("La diffusion a été enregistrée.")
        return render_template("message.html", message=_("Your broadcast has been saved."))

    return render_template("broadcast.html", form=form, stats=stats)

@app.route("/ban-appeal/", methods=["GET", "POST"])
def ban_appeal():
    if request.args.get("user_id") not in stats["codes"]["ban_appeal"].keys():
        return render_template("message.html", message=_("You have to be banned to have access to this page."))
    elif stats["codes"]["ban_appeal"][request.args.get("user_id")] != request.args.get("appeal_code"):
        app.logger.info(f"{request.args.get['user_id']} a essayé de faire la malin en changeant le html des hidden inputs sur la page de demande de débannissement.")
        return render_template("message.html", message=_("Hey smartass, quit trying."))

    form = BanAppealForm()
    
    if form.validate_on_submit():
        user = load_user(form.user_id.data, active=False)
        if user.ban_appeal:
            app.logger.info(f"{form.user_id.data} a essayé de faire une demande de débannissement alors qu'il en a déja fait une.")
            return render_template("message.html", message=_("You have already made a ban appeal."))

        user.ban_appeal = form.reason.data
        user.uexport(u_cont)

        stats["codes"]["ban_appeal"].pop(request.args.get("user_id"))
        stuffimporter.set_stats(stats)

        requests.get(config["telegram_send_url"] + "ban+appeal+received")
        app.logger.info("Une demande de débannissment a été enregistrée.")
        return render_template("message.html", message=_("Your ban appeal has been saved, it will be reviewed shortly."))

    return render_template("banned.html", form=form, user_id=request.args.get("user_id"))

@app.route("/about/")
def about():
    return render_template("about.html")

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

    current_user.uexport(u_cont)
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
    user_id = HiddenField(validators=[
        validators.InputRequired(),
        validators.AnyOf([stats["broadcast"]["author"]])
    ])

    message = TextAreaField(lazy_gettext("Enter the message you want to send to this websites users."), validators=[
        validators.InputRequired(),
        validators.Length(0, 512),
        MinWords(2, message=lazy_gettext("I'm sorry but you are going to have to write more than one word."))
    ])

    display_name = StringField(lazy_gettext("Author of this message (name that you want to be designated as that everyone will see.):"), validators=[
        validators.InputRequired(),
        validators.Length(0, 64)
    ])

    brod_code = StringField(lazy_gettext("Verification code from the email you received:"), validators=[
        validators.InputRequired(),
        validators.Length(43, 43),
        validators.AnyOf([stats["codes"]["broadcast"]], message=lazy_gettext("You have to input the code you received in the mail we sent to you."))
    ])

    submit = SubmitField(lazy_gettext("Submit"))

class BanAppealForm(FlaskForm):
    user_id = HiddenField(validators=[
        validators.InputRequired(),
        validators.AnyOf(stats["codes"]["ban_appeal"].keys(), message=lazy_gettext("You have to be banned to submit this form."))
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
    verif_code = HiddenField()

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
    verif_code = HiddenField()

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
def admin_panel():
    global stats
    identifier = current_user.id_ if current_user.is_authenticated else request.remote_addr

    if request.args.get("touma") != "toumatoumatoutoumatoumateo" or request.args.get("pouma") != "poumapoumatoupoumapoumateo" :
        app.logger.warning(f"{identifier} est arrivé sur l'admin panel.")
        abort(404)

    try:
        banned_user = u_cont.query_items("SELECT * FROM Users u WHERE IS_DEFINED(u.ban) AND u.ban.appeal <> '' OFFSET 0 LIMIT 1", enable_cross_partition_query=True).next()
    except StopIteration:
        banned_user = anon_user_getter()
        banned_user.id_ = "no_ban_appeal"

    banunban = BanUnbanForm()
    appealview = AppealViewForm()

    if request.method == "POST":
        if banunban.submit.data and banunban.verify():
            if banunban.verif_code.data != stats["codes"]["admin_action"]:
                app.logger.warning(f"{identifier} a essayé de faire une requête post sur l'admin panel.")
                abort(404)

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

                app.logger.info(f"{identifier} a banni {user.id_} avec succès.")
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

                app.logger.info(f"{identifier} a débanni {user.id_} avec succès.")

            user.uexport(u_cont)
            stuffimporter.set_stats(stats)
            
        elif appealview.submit.data and appealview.verify():
            if appealview.verif_code.data != stats["codes"]["admin_action"]:
                app.logger.warning(f"{identifier} a essayé de faire une requête post sur l'admin panel.")
                abort(404)

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
                app.logger.info(f"{identifier} a accepté la demande de débannissement de {user.id_} avec succès.")
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
            request.files[filename].stream.close()
        elif request.form["action"] == "export_stats":
            return stats
        elif request.form["action"] == "import_logs":
            filename = list(request.files.to_dict().keys())[0]
            with open("./logs.log", "wb") as logs_file:
                logs_file.write(request.files[filename].stream.read())
            request.files[filename].stream.close()
        elif request.form["action"] == "export_logs":
            return send_file("logs.log", as_attachment=True)

        return render_template("message.html", message="Succès de l'action " + request.form["action"])

    code = secrets.token_urlsafe(32)
    stats["codes"]["admin_action"] = secrets.token_urlsafe(32)
    stuffimporter.set_stats(stats)

    app.logger.info(f"{identifier} a accédé au panneau d'administration avec succès.")
    return render_template("admin_panel.html", verif_code=code, banunban=banunban, appealview=appealview, banned_user=banned_user)

# Error handling
@app.errorhandler(401)
def method_not_allowed(e):
    return render_template("error.html",
                            err_title="401 Unauthorized",
                            err_img_src="/static/img/you shall not pass.gif",
                            err_img_alt="Gandalf you shall not pass GIF",
                            err_msg=e), 401

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html",
                            err_title="404 Not Found",
                            err_img_src="/static/img/confused travolta.gif",
                            err_img_alt="Confused Travolta GIF",
                            err_msg=e), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("error.html",
                            err_title="500 Internal Server Error",
                            err_img_src="/static/img/this is fine.gif",
                            err_img_alt="This is fine dog GIF",
                            err_msg=e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=testing)