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
from flask import (
    Flask,
    redirect,
    render_template,
    url_for,
    session,
    request,
    abort,
    send_file
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf import (
    FlaskForm
)
from wtforms.fields import (
    StringField,
    TextAreaField,
    HiddenField,
    RadioField,
    SubmitField,
    BooleanField
)
from wtforms import validators
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

# Config setup
config = _stuffimporter.StuffImporter.get_config()

# Deepl translation setup
translator = deepl.Translator(config["deepl_auth_key"])

LANGUAGE_CODES = [lang.code.lower() for lang in translator.get_source_languages()]
SUPPORTED_LANGUAGES = ["en"]

# Database setup
cc = CosmosClient(config["db"]["url"], config["db"]["key"])
db = cc.get_database_client("Main Database")
u_cont = db.get_container_client("Web RBS Users")
p_cont = db.get_container_client("Web RBS Posts")

stuffimporter = _stuffimporter.StuffImporter(u_cont)

# Stats setup
global stats
stats = stuffimporter.get_stats()
stats["time"]["start_time"] = time.time()
stuffimporter.set_stats(stats)

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
    global stats
    skip_save = False
    if stats["broadcast"]["content"] == "[deleted]" and stats["broadcast"]["author_name"] == "[deleted]":
        skip_save = True
    elif stats["time"]["last_broadcaster"] + 86400 > time.time():
        app.logger.debug("Le diffuseur a toujours du temps pour faire sa diffusion.")
        return func
    elif stats["time"]["last_broadcast"] < stats["time"]["last_broadcaster"] and stats["time"]["last_broadcast"] + 86400 > time.time():
        app.logger.debug("Le diffuseur a fait sa diffusion et le temps du post n'est pas terminé.")
        return func

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
            new_post["ratio"] = 1
        p_cont.upsert_item(new_post)

        # Update stats in relation of the current post
        stats["broadcasts"]["msgs_sent"] += 1
        try:
            stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] += 1
        except KeyError:
            stats["broadcasts"]["langs_msgs_sent"][new_post["lang"]] = 1

        stats["broadcasts"]["words_sent"] += len(re.findall(r"[\w']+", new_post["content"]))
        stats["broadcasts"]["characters_sent"] += len(new_post["content"])
    
    # Select another broadcaster
    stats["broadcast"]["author"] = random.choice(stuffimporter.pot_brods(stats["broadcast"]["author"]))
    stats["broadcast"]["author_name"] = ""
    stats["broadcast"]["content"] = ""
    stats["broadcast"]["date"] = ""

    stats["time"]["last_broadcaster"] = time.time()

    code = secrets.token_urlsafe(32)
    stats["codes"]["broadcast"] = code

    brod = load_user(stats["broadcast"]["author"], active=False)
    if not brod.email:
        stats = stuffimporter.rollback_stats()
        app.logger.error(f"L'utilisateur sélectionné {brod.id_} n'a pas d'email.")
        return func

    # Send mail to the new broadcaster
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

    stuffimporter.set_stats(stats)

    app.logger.info(f"Nouveau diffuseur {brod.id_} a été sélectionné.")
    return func

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
            return render_template(f"{lang}/message.html", message=
            {"en": "Double accounts aren't allowed.",
            "fr": "Les doubles comptes ne sont pas autorisés."}[lang])
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

        return redirect(url_for("ban_appeal", lang=lang, user_id=user.id_, appeal_code=code))

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

@app.route("/<lang>/", methods=["GET", "POST"])
@verify_broadcast
def index(lang):
    if lang not in LANGUAGE_CODES:
        abort(404)

    if lang not in SUPPORTED_LANGUAGES:
        set_lang("en")
        return render_template("en/message.html", message="This language has not been implemented yet.")

    form = ReportForm()
    
    if form.validate_on_submit(): # Report callback
        if not stats["broadcast"]["content"]:
            app.logger.warning(f"{current_user.id_} a essayé de signaler un post alors qu'il n'y en a pas.")
            return render_template(f"{lang}/message.html", message=
            {"en": "No post is live right now so you can't report one.",
            "fr": "Aucun post n'est en train d'être noté donc tu ne peux pas le signaler."}[lang])
        elif current_user.report_post_id == stats["broadcast"]["id"]:
            app.logger.debug(f"{current_user.id_} a essayé de resignaler le post.")
            return render_template(f"{lang}/message.html", message=
            {"en": "You have already reported this post so you can't report it again.",
            "fr": "Vous avez déja signalé ce post, vous ne pouvez pas le signaler une deuxième fois."}[lang])

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

            with open(f"templates/ban_mail.html", "r", encoding="utf-8") as mail_file:
                mail_content = mail_file.read()
            mail_content = mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net").replace("{{ brod.ban_message }}", brod.ban_message).replace("{{ brod.ban_reason }}", brod.ban_reason).replace("{{ brod.ban_most_quoted }}", brod.ban_most_quoted)

            message = Mail(
                from_email="random.broadcasting.selector@gmail.com",
                to_emails=brod.email,
                subject="RandomBroadcastingSelector : You were banned.",
                html_content=mail_content
            )
            sg_client.send(message)

            stats["users"]["banned"] += 1

            # Delete the banned user's message
            stats["broadcast"]["author_name"] = "[deleted]"
            stats["broadcast"]["content"] = "[deleted]"

            app.logger.info(f"Le diffuseur {brod.id_} a été banni.")

        stuffimporter.set_stats(stats)

        return render_template(f"{lang}/message.html", message=
        {"en": "Your report as been saved.",
        "fr": "Votre signalement a été enregistré."}[lang])

    set_lang(lang)
    return render_template(f"{lang}/index.html", stats=stats, form=form)

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
    if request.args.get("denied"):
        lang = get_lang()
        return render_template(f"{lang}/message.html", message=
        {"en": "You cancelled the Continue with Twitter action.",
        "fr": "Vous avez annulé l'action Continuer avec Twitter."}[lang])

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
    if request.args.get("error") == "access_denied":
        lang = get_lang()
        return render_template(f"{lang}/message.html", message=
        {"en": "You cancelled the Continue with Discord action.",
        "fr": "Vous avez annulé l'action Continuer avec Discord."}[lang])

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

@app.route("/logout/")
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
        
        stats["top_posts"]["5_most_upped"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.upvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_downed"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.downvotes DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_pop"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio DESC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        stats["top_posts"]["5_most_unpop"] = stuffimporter.itempaged_to_list(p_cont.query_items("SELECT * FROM Posts p ORDER BY p.ratio ASC OFFSET 0 LIMIT 5", enable_cross_partition_query=True))
        
        stats["time"]["stats_last_edited"] = time.time()
        stats["time"]["stats_getting"] = time.time() - start_time

        app.logger.debug("Les stats ont étés mis a jour")

    stats["time"]["uptime_str"] = stuffimporter.seconds_to_str(time.time() - stats["time"]["start_time"])

    stuffimporter.set_stats(stats)

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

    app.logger.debug("Fichier stats exporté.")
    return stats_file

@app.route("/<lang>/broadcast/", methods=["GET", "POST"])
@login_required
def broadcast(lang):
    if current_user.id_ != stats["broadcast"]["author"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have to be broadcaster to have access to this page.",
        "fr": "Vous devez être diffuseur pour accéder a cette page."}[lang])
    elif stats["broadcast"]["content"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "You have already made your broadcast.",
        "fr": "Vous avez déja fait votre diffusion."}[lang])

    form = BroadcastForm()
    
    if form.validate_on_submit():
        stats["codes"]["broadcast"] = ""

        stats["broadcast"]["id"] = int(stats["broadcast"]["id"]) + 1
        stats["broadcast"]["content"] = form.message.data
        stats["broadcast"]["author_name"] = form.display_name.data
        stats["broadcast"]["date"] = str(datetime.datetime.today().date())
    
        test = translator.translate_text(form.message.data, target_lang="EN-US")
        stats["broadcast"]["lang"] = test.detected_source_lang.lower()
    
        for language in translator.get_target_languages():
            lang_code = language.code
            if len(lang_code) != 2:
                lang_code = lang_code.split("-")[0]
            stats["broadcast"]["trads"][lang_code.lower()] = translator.translate_text(form.message.data, target_lang=language.code).text
        
        stats["time"]["last_broadcast"] = time.time()
    
        stuffimporter.set_stats(stats)
    
        app.logger.info("La diffusion a été enregistrée.")
        return render_template(f"{lang}/message.html", message=
        {"en": "Your broadcast has been saved.",
        "fr": "Votre diffusion a été enregistrée."}[lang])

    set_lang(lang)
    return render_template(f"{lang}/broadcast.html", form=form, stats=stats)

@app.route("/<lang>/ban-appeal/", methods=["GET", "POST"])
def ban_appeal(lang):
    if request.args.get("user_id") not in stats["codes"]["ban_appeal"].keys():
        return render_template(f"{lang}/message.html", message=
        {"en": "You have to be banned to have access to this page.",
        "fr": "Vous devez être banni pour accéder a cette page."}[lang])
    elif stats["codes"]["ban_appeal"][request.args.get("user_id")] != request.args.get("appeal_code"):
        app.logger.info(f"{request.args.get['user_id']} a essayé de faire la malin en changeant le html des hidden inputs sur la page de demande de débannissement.")
        return render_template(f"{lang}/message.html", message=
        {"en": "Hey smartass, quit trying.",
        "fr": "Hé petit.e malin.e, arrête d'essayer."}[lang])

    form = BanAppealForm()
    
    if form.validate_on_submit():
        user = load_user(form.user_id.data, active=False)
        if user.ban_appeal:
            app.logger.info(f"{form.user_id.data} a essayé de faire une demande de débannissement alors qu'il en a déja fait une.")
            return render_template(f"{lang}/message.html", message=
            {"en": "You have already made a ban appeal.",
            "fr": "Vous avez déja fait une demande de débannissement."}[lang])

        user.ban_appeal = form.reason.data
        user.uexport(u_cont)

        stats["codes"]["ban_appeal"].pop(request.args.get("user_id"))
        stuffimporter.set_stats(stats)

        requests.get(config["telegram_send_url"] + "ban+appeal+received")
        app.logger.info("Une demande de débannissment a été enregistrée.")
        return render_template(f"{lang}/message.html", message=
        {"en": "Your ban appeal has been saved, it will be reviewed shortly.",
        "fr": "Votre demande de débannissement a été enregistrée, elle sera examinée dans les plus brefs délais."}[lang])

    set_lang(lang)
    return render_template(f"{lang}/banned.html", form=form, user_id=request.args.get("user_id"))

# Callbacks
@app.route("/vote", methods=["POST"])
@login_required
def upvote_callback():
    lang = get_lang()
    if not stats["broadcast"]["content"]:
        return render_template(f"{lang}/message.html", message=
        {"en": "No post is live right now so you can't vote.",
        "fr": "Aucun post n'est en train d'être noté donc tu ne peux pas voter."}[lang])

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

        current_user.uexport(u_cont)
        stuffimporter.set_stats(stats)

        return "upvote"
    else:
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

        return "downvote"

# Custom validators
class MinWords(object):
    def __init__(self, minimum=-1, message=None):
        self.minimum = minimum
        if not message:
            message = f'Field must have at least {minimum} words.'
        self.message = message

    def __call__(self, form, field):
        words = field.data and len(re.findall(r"[\w']+", field.data)) or 0
        if words < self.minimum:
            raise validators.ValidationError(self.message)

class InString(object):
    def __init__(self, string="", message=None):
        self.string = string
        if not message:
            message = f'Field must be included in "{string}".'
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

    message = TextAreaField("Enter the message you want to send to this websites users.", validators=[
        validators.InputRequired(),
        validators.Length(0, 512),
        MinWords(2, message="I'm sorry but you are going to have to write more than one word.")
    ])

    display_name = StringField("Author of this message (name that you want to be designated as that everyone will see.) :", validators=[
        validators.InputRequired(),
        validators.Length(0, 64)
    ])

    brod_code = StringField("Verification code from the email you received :", validators=[
        validators.InputRequired(),
        validators.Length(43, 43),
        validators.AnyOf([stats["codes"]["broadcast"]], message="You have to input the code you received in the mail we sent to you.")
    ])

    submit = SubmitField()

class BanAppealForm(FlaskForm):
    user_id = HiddenField(validators=[
        validators.InputRequired(),
        validators.AnyOf(stats["codes"]["ban_appeal"].keys(), message="You have to be banned to submit this form.")
    ])

    reason = TextAreaField("Enter why you should be unbanned.", validators=[
        validators.InputRequired(),
        validators.Length(0, 512),
        MinWords(2, message="If you really want to get unbanned you should write a bit more than that (more than one word).")
    ])

    submit = SubmitField()

class ReportForm(FlaskForm):
    reason = RadioField(choices=[
        ("harassement", "Is this broadcast harassing, insulting or encouraging hate against anyone ?"),
        ("mild_language", "Is this broadcast using too much mild language for a family friendly website ?"),
        ("link", 'Does this broadcast contain any link (like "http://example.com") or pseudo link (like "example.com") or attempts at putting a link that doesn\'t look like one (like "e x a m p l e . c o m" or "example dot com") ?'),
        ("offensive_name", "Has this broadcasts author chosen an offending name ?")
    ], validators=[
        validators.InputRequired(),
    ])
    
    message_quote = StringField(validators=[
        StopIfBlah(),
        validators.InputRequired(),
        InString(stats["broadcast"]["content"], message="The quote you supplied isn't in the broadcast."),
        MinWords(2, message="The quote you supplied has only got one word when it has to have at least two.")
    ])

    submit = SubmitField()

class BanUnbanForm(FlaskForm):
    verif_code = HiddenField()

    user_id = StringField("Id de la personne concernée : ", validators=[
        validators.InputRequired()
    ])

    whatodo = RadioField(choices=[
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
            if banunban.whatodo.data == "ban":
                if user.is_broadcaster:
                    # Delete the banned user's message
                    stats["broadcast"]["author_name"] = "[deleted]"
                    stats["broadcast"]["content"] = "[deleted]"

                user.banned = 1
                user.ban_message = banunban.ban_message.data
                user.ban_reason = banunban.ban_reason.data
                user.ban_most_quoted = banunban.ban_most_quoted.data

                if not banunban.slienced.data:
                    with open(f"templates/ban_mail.html", "r", encoding="utf-8") as mail_file:
                        mail_content = mail_file.read()
                    mail_content = mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net").replace("{{ user.ban_message }}", user.ban_message).replace("{{ user.ban_reason }}", user.ban_reason).replace("{{ user.ban_most_quoted }}", user.ban_most_quoted)

                    message = Mail(
                        from_email="random.broadcasting.selector@gmail.com",
                        to_emails=user.email,
                        subject="RandomBroadcastingSelector : You were banned.",
                        html_content=mail_content
                    )
                    sg_client.send(message)

                stats["users"]["banned"] += 1

                app.logger.info(f"{identifier} a banni {user.id_} avec succès.")
            else:
                user = load_user(banunban.user_id.data, active=False)
                user.banned = 0

                if not banunban.slienced.data:
                    with open(f"templates/unban_mail.html", "r", encoding="utf-8") as mail_file:
                        mail_content = mail_file.read()
                    mail_content = mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net")

                    message = Mail(
                        from_email="random.broadcasting.selector@gmail.com",
                        to_emails=user.email,
                        subject="RandomBroadcastingSelector : You are no longer banned.",
                        html_content=mail_content
                    )
                    sg_client.send(message)

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
                    with open(f"templates/unban_mail.html", "r", encoding="utf-8") as mail_file:
                        mail_content = mail_file.read()
                    mail_content = mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net")

                    message = Mail(
                        from_email="random.broadcasting.selector@gmail.com",
                        to_emails=user.email,
                        subject="RandomBroadcastingSelector : You are no longer banned.",
                        html_content=mail_content
                    )
                    sg_client.send(message)

                stats["users"]["banned"] -= 1

                stuffimporter.set_stats(stats)
                app.logger.info(f"{identifier} a accepté la demande de débannissement de {user.id_} avec succès.")
            else:
                user = load_user(appealview.user_id.data, active=False)
                user.ban_appeal = ""

                if not appealview.slienced.data:
                    with open(f"templates/refused_mail.html", "r", encoding="utf-8") as mail_file:
                        mail_content = mail_file.read()
                    mail_content = mail_content.replace("{{ server_name }}", "rbs.azurewebsites.net")

                    message = Mail(
                        from_email="random.broadcasting.selector@gmail.com",
                        to_emails=user.email,
                        subject="RandomBroadcastingSelector : Your ban appeal was refused.",
                        html_content=mail_content
                    )
                    sg_client.send(message)

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

        return render_template("en/message.html", message="Succès de l'action " + request.form["action"])

    code = secrets.token_urlsafe(32)
    stats["codes"]["admin_action"] = secrets.token_urlsafe(32)
    stuffimporter.set_stats(stats)

    app.logger.info(f"{identifier} a accédé au panneau d'administration avec succès.")
    return render_template("admin_panel.html", verif_code=code, banunban=banunban, appealview=appealview, banned_user=banned_user)

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
    app.run(host="0.0.0.0", debug=True)