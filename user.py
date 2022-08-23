from azure.cosmos.exceptions import *
import json

class User:
    def __init__(self, id_="", name="", email="", lang="en") -> None:
        self.id_ = id_
        self.name = name
        self.email = email
        self.lang = lang
        self.upvote = ""
        self.downvote = ""
        self.last_active = 0

        self.banned = 0
        self.ban_message = ""
        self.ban_reason =  ""
        self.ban_most_quoted = ""
        self.ban_appeal = ""

        self.report_post_id = ""
        self.report_reason = ""
        self.report_quote = ""

        self.is_active = True
        self.is_authenticated = False
        self.is_anonymous = False
        self.is_broadcaster = False

    def get_id(self) -> str:
        return self.id_

    def uimport(self, u_cont, user_id:str) -> None:
        """
        Use this functions when sure the user is authenticated
        """
        try:
            user = u_cont.read_item(user_id, partition_key=user_id)
        except CosmosResourceNotFoundError:
            return None

        self.id_ = user["id"]
        self.name = user["name"]
        self.email = user["email"]
        self.lang = user["lang"]
        self.upvote = user["upvote"]
        self.downvote = user["downvote"]
        self.last_active = user["last_active"]

        if user.get("ban"):
            self.banned = 1
            self.ban_message = user["ban"]["message"]
            self.ban_reason =  user["ban"]["reason"]
            self.ban_most_quoted = user["ban"]["most_quoted"]
            self.ban_appeal = user["ban"]["appeal"]

        if user.get("report"):
            self.report_post_id = user["report"]["post_id"]
            self.report_reason = user["report"]["reason"]
            self.report_quote = user["report"]["quote"]
        
        self.is_active = not bool(self.banned)
        self.is_authenticated = True
        self.is_anonymous = False
        self.is_broadcaster = False

        return True

    def uexport(self, u_cont):
        with open("samples/sample_user_part.json", "r", encoding="utf-8") as sample_user:
            user = json.load(sample_user)

        user["id"] = self.id_
        user["name"] = self.name
        user["email"] = self.email
        user["lang"] = self.lang
        user["upvote"] = self.upvote
        user["downvote"] = self.downvote
        user["last_active"] = self.last_active

        if self.banned:
            user["ban"] = {}
            user["ban"]["message"] = self.ban_message
            user["ban"]["reason"] = self.ban_reason
            user["ban"]["most_quoted"] = self.ban_most_quoted
            user["ban"]["appeal"] = self.ban_appeal

        if self.report_post_id:
            user["report"] = {}
            user["report"]["post_id"] = self.report_post_id
            user["report"]["reason"] = self.report_reason
            user["report"]["quote"] = self.report_quote

        u_cont.upsert_item(user)

        return True