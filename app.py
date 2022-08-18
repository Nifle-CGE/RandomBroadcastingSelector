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
from flask import Flask, redirect, render_template, url_for, session, request, abort
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
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
app.logger.level = logging.DEBUG

app.logger.info("Je suis prêt à être prêt.")

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

# Config elements setup
config = _stuffimporter.get_json("config")
stats = _stuffimporter.get_json("stats")
stats["time"]["start_time"] = time.time()
_stuffimporter.set_stats(stats)

# Deepl translation setup
translator = deepl.Translator(config["deepl_auth_key"])

LANGUAGE_CODES = [lang.code.lower() for lang in translator.get_source_languages()]
SUPPORTED_LANGUAGES = ["en"]

# Database setup
cc = CosmosClient(config["db"]["url"], config["db"]["key"])
db = cc.get_database_client("Main Database")
u_cont = db.get_container_client("Web RBS Users")
p_cont = db.get_container_client("Web RBS Posts")

# Mail client setup
sg_client = SendGridAPIClient(config["sendgrid_api_key"])

# OAuth setup
#app.config["SERVER_NAME"] = "rbs.azurewebsites.net"
oauth = OAuth(app)

app.logger.info("Je suis prêt.")

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

# Useful defs
def verify_broadcast(func):
    if stats["time"]["last_broadcaster"] + 86400 > time.time():
        app.logger.info("The broadcaster still has time to make his broadcast.")
        return func
    elif stats["time"]["last_broadcast"] < stats["time"]["last_broadcaster"] and stats["time"]["last_broadcast"] + 86400 > time.time():
        app.logger.info("The broadcaster has made his broadcast and this posts time isn't over yet.")
        return func

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
        new_post["ratio"] = 1
    p_cont.create_item(new_post)

    stats["broadcast"]["author"] = random.choice(_stuffimporter.pot_brods(u_cont, stats["broadcast"]["author"]))
    stats["broadcast"]["author_name"] = ""
    stats["broadcast"]["content"] = ""
    stats["broadcast"]["date"] = ""

    stats["broadcasts"]["msgs_sent"] += 1
    try:
        stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] += 1
    except KeyError:
        stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] = 1

    stats["broadcasts"]["words_sent"] += len(re.findall(r"[\w']+", new_post["content"]))
    stats["broadcasts"]["characters_sent"] += len(new_post["content"])
    
    stats["time"]["last_broadcaster"] = time.time()

    code = secrets.token_urlsafe(32)
    stats["codes"]["broadcast"] = code

    _stuffimporter.set_stats(stats)

    brod = load_user(stats["broadcast"]["author"], active=False)
    if not brod.email:
        app.logger.error(f"Selected user => {brod.id_} doesn't have an email.")
        return func

    with open(f"templates/brod_mail.html", "r", encoding="utf-8") as mail_file:
        mail_content = mail_file.read()
    mail_content = mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net").replace("{{ brod_code }}", code)

    message = Mail(
        from_email="random.broadcasting.selector@gmail.com",
        to_emails=brod.email,
        subject="RandomBroadcastingSelector : You are the one.",
        html_content=mail_content
    )
    sg_client.send(message)

    app.logger.info(f"New broadcaster selected => {brod.id_}.")
    return func

def login_or_create_user(id_:str, name:str, email:str, lang:str):
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"

    # Test to see if the user exists in the db
    user = load_user(id_)

    # Doesn't exist? Add it to the database.
    if not user:
        try:
            fraud_id = u_cont.query_items(f"SELECT u.id FROM Users u WHERE u.email = '{email}'", enable_cross_partition_query=True).next()
            app.logger.info(f"Double compte empéché => {fraud_id}.")
            return render_template(f"{lang}/message.html", message=
            {"en": "Double accounts aren't allowed.",
            "fr": "Les doubles comptes ne sont pas autorisés."}[lang])
        except StopIteration:
            pass

        new_user = User(id_=id_, name=name, email=email)
        new_user.last_active = time.time()
        new_user.uexport(u_cont)

        stats["users"]["num"] += 1
        _stuffimporter.set_stats(stats)

        user = new_user

        app.logger.info(f"User created => {user.id_}.")
    if user.banned: # if user banned send the ban appeal form
        code = secrets.token_urlsafe(32)
        stats["codes"]["ban_appeal"].append(code)
        _stuffimporter.set_stats(stats)

        return render_template(f"{lang}/banned.html", user_id=user.id_, appeal_code=code)

    # Begin user session by logging the user in
    user.is_authenticated = True
    login_user(user)

    # Send user back to homepage
    set_lang(lang)
    return redirect(url_for("index", lang=lang))

def get_lang():
    lang = session.get("lang")
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"
        session["lang"] = lang

    return lang

def set_lang(lang):
    if lang not in SUPPORTED_LANGUAGES:
        lang = "en"

    session["lang"] = lang

# Routing
@app.route("/")
def index_redirect():
    return redirect(url_for("index", lang=get_lang()))

@app.route("/<lang>/")
@verify_broadcast
def index(lang):
    if lang not in LANGUAGE_CODES:
        abort(404)

    if lang not in SUPPORTED_LANGUAGES:
        set_lang("en")
        return render_template("en/message.html", message="This language has not been implemented yet.")

    set_lang(lang)
    return render_template(f"{lang}/index.html", stats=stats)

# All the login stuff
@app.route("/<lang>/login/")
@verify_broadcast
def login(lang):
    return render_template(f"{lang}/login.html")

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
        return "User email not available or not verified by Google.", 400
    
    unique_id = "gg-" + response_json["sub"]
    users_name = response_json["name"]
    users_email = response_json["email"]
    lang = response_json["locale"]
    if lang not in LANGUAGE_CODES:
        lang = "en"

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
    token = oauth.twitter.authorize_access_token()
    response = oauth.twitter.get("account/verify_credentials.json", params={"include_email": "true", "skip_status": "true"})
    response_json = response.json()

    unique_id = "tw-" + response_json["id_str"]
    users_name = response_json["name"]
    users_email = response_json.get("email")
    if not users_email:
        return "User email not available or not verified by Twitter.", 400

    settings_response = oauth.twitter.get("account/settings.json")
    settings_response_json = settings_response.json()
    lang = settings_response_json.get("language")
    if lang not in LANGUAGE_CODES:
        lang = "en"

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

    unique_id = "gh-" + str(response_json["id"])
    users_name = response_json["name"]
    users_email = response_json["email"]
    lang = "en"

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
    token = oauth.discord.authorize_access_token()
    response = oauth.discord.get("users/@me")
    response_json = response.json()

    if not response_json.get("verified"):
        return "User email not available or not verified by Discord.", 400
    
    unique_id = "di-" + response_json["id"]
    users_name = response_json["username"]
    users_email = response_json["email"]
    lang = response_json["locale"]
    if lang not in LANGUAGE_CODES:
        lang = "en"

    return login_or_create_user(unique_id, users_name, users_email, lang)

"""
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

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index", lang=get_lang()))

# General stuff
@app.route("/<lang>/history/<int:page>")
@verify_broadcast
def history(lang, page):
    set_lang(lang)

    post_list = []
    for post_id in range((5 * page) - 4, (5 * page) + 1):
        try:
            post_list.append(p_cont.query_items(f"SELECT * FROM Posts p WHERE p.id = '{post_id}'", enable_cross_partition_query=True).next())
        except StopIteration:
            pass
    
    return render_template(f"{lang}/history.html", post_list=post_list, hist_page=int(page))

@app.route("/<lang>/post/")
@verify_broadcast
def specific_post_search(lang):
    set_lang(lang)

    max_id = int(stats["broadcast"]["id"]) - 1
        
    return render_template(f"{lang}/post_search.html", max_post_id=max_id)

@app.route("/<lang>/post/<int:id>")
@verify_broadcast
def specific_post(lang, id):
    set_lang(lang)

    try:
        post = p_cont.query_items(f"SELECT * FROM Posts p WHERE p.id = '{id}'", enable_cross_partition_query=True).next()
    except StopIteration:
        abort(404)

    return render_template(f"{lang}/post.html", post=post)

@app.route("/<lang>/statistics/")
@verify_broadcast
def statistics(lang):
    if stats["time"]["stats_last_edited"] + 600 < time.time():
        start_time = time.time()

        stats["users"]["seen_msg"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {stats['time']['last_broadcast']}", enable_cross_partition_query=True).next()
        stats["users"]["lastact_hour"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 3600}", enable_cross_partition_query=True).next()
        stats["users"]["lastact_24h"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 86400}", enable_cross_partition_query=True).next()
        stats["users"]["lastact_week"] = u_cont.query_items(f"SELECT VALUE COUNT(1) FROM Users u WHERE u.last_active > {time.time() - 604800}", enable_cross_partition_query=True).next()
        
        stats["top_posts"]["5_most_upped"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.upvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_downed"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.downvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_pop"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_unpop"] = _stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio ASC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        
        stats["time"]["stats_last_edited"] = time.time()
        stats["time"]["stats_getting"] = time.time() - start_time

    stats["time"]["uptime_str"] = _stuffimporter.seconds_to_str(time.time() - stats["time"]["start_time"])

    _stuffimporter.set_stats(stats)

    set_lang(lang)
    return render_template(f"{lang}/stats.html", stats=stats)

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

    app.logger.info("Stats file exported.")
    return stats_file

@app.route("/<lang>/broadcast/")
@login_required
def broadcast(lang):
    if current_user.id_ != stats["broadcast"]["author"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have to be broadcaster to have access to this page.",
        "fr": "Vous devez être diffuseur pour accéder a cette page."}[lang])

    if stats["broadcast"]["content"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have already made your broadcast.",
        "fr": "Vous avez déja fait votre diffusion."}[lang])

    set_lang(lang)
    return render_template(f"{lang}/broadcast.html", stats=stats)

# Callbacks
@app.route("/broadcast-callback", methods=["POST"])
@login_required
def broadcast_callback():
    lang = get_lang()
    
    if stats["codes"]["broadcast"] != request.form["brod_code"]:
        app.logger.info("Code de vérif incorrect.")
        return render_template(f"{lang}/message.html", message=
        {"en": "You have to input the code you received in the mail we sent to you.",
        "fr": "Vous devez saisir le code que vous avez reçu dans le mail qui vous a été envoyé."}[lang])
    else:
        stats["codes"]["broadcast"] = ""
    
    if request.form["user_id"] != stats["broadcast"]["author"]:
        app.logger.info("HACKER ALERT BROD")
        return render_template(f"{lang}/message.html", message=
        {"en": "I didn't think it was possible but you did it, so anyway you can only broadcast if you are the broadcaster, which you are not.",
        "fr": "Je pensait pas que c'était possible mais tu l'a fait, bon, de toute façon tu peux pas diffuser si tu n'est pas diffuseur."}[lang])
    
    with open("samples/sample_post.json", "r", encoding="utf-8") as sample_file:
        new_post = json.load(sample_file)

    stats["broadcast"]["id"] = int(stats["broadcast"]["id"]) + 1
    stats["broadcast"]["content"] = request.form["message"]
    stats["broadcast"]["author_name"] = request.form["displayed_name"]
    stats["broadcast"]["date"] = str(datetime.datetime.today().date())

    test = translator.translate_text(request.form["message"], target_lang="EN-US")
    stats["broadcast"]["lang"] = test.detected_source_lang.lower()

    for language in translator.get_target_languages():
        lang_code = language.code
        if len(lang_code) != 2:
            lang_code = lang_code.split("-")[0]
        stats["broadcast"]["trads"][lang_code.lower()] = translator.translate_text(request.form["message"], target_lang=language.code).text
    
    stats["time"]["last_broadcast"] = time.time()

    _stuffimporter.set_stats(stats)

    app.logger.info("The broadcast has been saved.")
    return render_template(f"{lang}/message.html", message=
    {"en": "Your broadcast has been saved.",
    "fr": "Votre diffusion a été enregistrée."}[lang])

@app.route("/ban-appeal-callback", methods=["POST"])
def ban_appeal_callback():
    lang = get_lang()

    try:
        stats["codes"]["ban_appeal"].remove(request.form["appeal_code"])
        _stuffimporter.set_stats(stats)
    except ValueError:
        app.logger.info("HACKER ALERT BAN APPEAL")
        return render_template(f"{lang}/message.html", message=
        {"en": "Get IP banned noob.",
        "fr": "Tu est maintenant ban IP."}[lang])

    user = load_user(request.form["user_id"], active=False)
    if not user.ban_appeal:
        app.logger.info("Banned tryed to make another ban appeal.")
        return render_template(f"{lang}/message.html", message=
        {"en": "You have already made a ban appeal.",
        "fr": "Vous avez déja fait une demande de débannissement."}[lang])
    user.ban_appeal = request.form["reason"]
    user.uexport(u_cont)

    requests.get(config["auth"]["telegram_send_url"] + "ban+appeal+received")
    app.logger.info("Ban appeal saved.")
    return render_template(f"{lang}/message.html", message=
    {"en": "Your ban appeal has been saved.",
    "fr": "Votre demande de débannissement a été enregistrée."}[lang])

@app.route("/upvote-callback", methods=["POST"])
@login_required
def upvote_callback():
    lang = get_lang()
    if not stats["broadcast"]["content"]:
        return {"en": "No post is live right now so you can't upvote one.",
                "fr": "Aucun post n'est en train d'être noté donc tu ne peux pas l'upvoter."}[lang]

    if current_user.upvote == stats["broadcast"]["id"]:
        current_user.upvote = ""
        stats["broadcast"]["upvotes"] -= 1
    else:
        current_user.upvote = stats["broadcast"]["id"]
        stats["broadcast"]["upvotes"] += 1
        if current_user.downvote == stats["broadcast"]["id"]:
            current_user.downvote = ""
            stats["broadcast"]["downvotes"] -= 1

    current_user.uexport(u_cont)
    _stuffimporter.set_stats(stats)

    return "upvote"

@app.route("/downvote-callback", methods=["POST"])
@login_required
def downvote_callback():
    lang = get_lang()
    if not stats["broadcast"]["content"]:
        return {"en": "No post is live right now so you can't downvote one.",
                "fr": "Aucun post n'est en train d'être noté donc tu ne peux pas le downvoter."}[lang]

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
    _stuffimporter.set_stats(stats)

    return "downvote"

@app.route("/report-callback", methods=["POST"])
@login_required
def report_callback():
    lang = get_lang()
    if not stats["broadcast"]["content"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "No post is live right now so you can't report one.",
        "fr": "Aucun post n'est en train d'être noté donc tu ne peux pas le signaler."}[lang])

    if current_user.report_post_id == stats["broadcast"]["id"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have already reported this post and you can't report it again.",
        "fr": "Vous avez déja signalé ce post, vous ne pouvez pas le signaler une deuxième fois."}[lang])

    current_user.report_post_id = stats["broadcast"]["id"]
    current_user.report_reason = request.form["reason"]
    current_user.report_quote = request.form["message_quote"]

    current_user.uexport(u_cont)
    
    stats["broadcast"]["reports"] += 1

    if stats["users"]["seen_msg"] > (3 * math.sqrt(stats["users"]["num"])) and stats["broadcast"]["reports"] > (stats["users"]["seen_msg"] / 2):
        brod = load_user(stats["broadcast"]["author"], active=False)

        brod.banned = 1
        brod.ban_message = stats["broadcast"]["content"]

        reports = _stuffimporter.itempaged_to_list(u_cont.query_items("SELECT {'reason': u.report.reason, 'quote': u.report.quote} as user FROM Users u WHERE u.report.post_id = '" + stats['broadcast']['id'] + "'", enable_cross_partition_query=True))
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

        reason_quotes = [user["quote"] for user in reports if user["reason"] == most_reason]
        results = {}
        for quote in reason_quotes:
            results[quote] = 0
            for secquote in reason_quotes:
                if quote in secquote:
                    results[quote] += 1

        results = sorted(results.items(), key=lambda x:x[1])
        brod.ban_most_quoted = results[0][0]

        brod.uexport(u_cont)

        if brod.email:
            with open(f"templates/ban_mail.html", "r", encoding="utf-8") as mail_file:
                mail_content = mail_file.read()
            mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net")
            mail_content.replace("{{ brod.ban_message }}", brod.ban_message)
            mail_content.replace("{{ brod.ban_reason }}", brod.ban_reason)
            mail_content.replace("{{ brod.ban_most_quoted }}", brod.ban_most_quoted)

            message = Mail(
                from_email="random.broadcasting.selector@gmail.com",
                to_emails=brod.email,
                subject="RandomBroadcastingSelector : You were banned.",
                html_content=mail_content
            )
            sg_client.send(message)

        stats["users"]["banned"] += 1

    _stuffimporter.set_stats(stats)

    return render_template(f"{lang}/message.html", message=
    {"en": "Your report as been saved.",
    "fr": "Votre signalement a été enregistré."}[lang])

# Legal stuff
@app.route("/privacy-policy/")
def privacy_policy():
    return render_template("privacy_policy.html")

@app.route("/terms-of-service/")
def terms_of_service():
    return render_template("terms_of_service.html")

@app.route("/<lang>/sitemap/")
def sitemap(lang):
    render_template(f"{lang}/sitemap.html")

# Crawling control
@app.route("/robots.txt")
def robots():
    return render_template("robots.html")

# Health check
@app.route("/ping/")
def ping():
    return "App online", 200

# Error handling
@app.errorhandler(401)
def method_not_allowed(e):
    return render_template(f"{get_lang()}/error.html",
                            err_title="401 Unauthorized",
                            err_img_src="/static/img/you shall not pass.gif",
                            err_img_alt="Gandalf you shall not pass GIF",
                            err_msg=e), 401

@app.errorhandler(404)
def not_found(e):
    return render_template(f"{get_lang()}/error.html",
                            err_title="404 Not Found",
                            err_img_src="/static/img/confused travolta.gif",
                            err_img_alt="Confused Travolta GIF",
                            err_msg=e), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template(f"{get_lang()}/error.html",
                            err_title="500 Internal Server Error",
                            err_img_src="/static/img/this is fine.gif",
                            err_img_alt="This is fine dog GIF",
                            err_msg=e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0")