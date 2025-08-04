import os
import random


class StuffImporter(object):
    def __init__(self, s_cont, _, ngettext) -> None:
        self.s_cont = s_cont
        self._ = _
        self.ngettext = ngettext

    @staticmethod
    def get_config() -> dict:
        return {
            "telegram_send_url": os.getenv("TELEGRAM_SEND_URL"),
            "db": {
                "url": os.getenv("DB_URL"),
                "key": os.getenv("DB_KEY")
            },
            "google": {
                "oauth_id": os.getenv("GOOGLE_OAUTH_ID"),
                "oauth_secret": os.getenv("GOOGLE_OAUTH_SECRET"),
                "discovery_url": os.getenv("GOOGLE_DISCOVERY_URL")
            },
            "twitter": {
                "apiv1_key": os.getenv("TWITTER_APIV1_KEY"),
                "apiv1_secret": os.getenv("TWITTER_APIV1_SECRET")
            },
            "facebook": {
                "client_id": os.getenv("FACEBOOK_CLIENT_ID"),
                "client_secret": os.getenv("FACEBOOK_CLIENT_SECRET")
            },
            "github": {
                "client_id": os.getenv("GH_CLIENT_ID"),
                "client_secret": os.getenv("GH_CLIENT_SECRET")
            },
            "discord": {
                "client_id": os.getenv("DISCORD_CLIENT_ID"),
                "client_secret": os.getenv("DISCORD_CLIENT_SECRET")
            },
            "twitch": {
                "client_id": os.getenv("TWITCH_CLIENT_ID"),
                "client_secret": os.getenv("TWITCH_CLIENT_SECRET")
            },
            "email_password": os.getenv("EMAIL_PASSWORD"),
            "deepl_auth_key": os.getenv("DEEPL_AUTH_KEY")
        }

    def get_stats(self) -> dict:
        return self.s_cont.read_item("stats.json", "stats.json")

    def set_stats(self, stats: dict):
        self.s_cont.replace_item("stats.json", stats)

    def select_random_broadcaster(self, user_container, last_brod: str) -> str:
        brods_query = user_container.query_items(f"SELECT u.id FROM Users u WHERE NOT IS_DEFINED(u.ban) AND u.id <> '{last_brod}'", enable_cross_partition_query=True)
        brods = []
        while True:
            try:
                brods.append(brods_query.next()["id"])
            except StopIteration:
                break

        return random.choice(brods)

    def seconds_to_str(self, seconds: float) -> str:
        days = round(seconds // 86400)
        hours = round((seconds % 86400) // 3600)
        minutes = round(((seconds % 86400) % 3600) // 60)
        rem_seconds = round(((seconds % 86400) % 3600) % 60)

        result = []
        if days:
            result.append(self.ngettext("%(num)s day", "%(num)s days", days))
        if days or hours:
            result.append(self.ngettext("%(num)s hour", "%(num)s hours", hours))
        if days or hours or minutes:
            result.append(self.ngettext("%(num)s minute", "%(num)s minutes", minutes))
        if days or hours or minutes or rem_seconds:
            result.append(self.ngettext("%(num)s second", "%(num)s seconds", rem_seconds))

        return ", ".join(result[:-1]) + " " + self._("and") + " " + result[-1] if len(result) > 1 else result[0]

    def itempaged_to_list(self, itempaged) -> list:
        result = []
        while True:
            try:
                result.append(itempaged.next())
            except StopIteration:
                return result
