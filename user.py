from azure.cosmos.exceptions import *
import json

class User:
    def __init__(self, id_=None, name=None, email=None) -> None:
        self.id_ = id_
        self.name = name
        self.email = email
        self.upvote = 0
        self.downvote = 0
        self.last_active = 0
        self.banned = 0
        self.ban_message = ""
        self.sample_reports = [] 
        self.ban_reason =  ""
        self.ban_appeal = ""
        self.report_post_id = 0
        self.report_reason = ""
        self.is_active = True
        self.is_authenticated = False
        self.is_anonymous = False
        self.is_broadcaster = False

    def get_id(self) -> str:
        return self.id_

    def import_user(self, u_cont, user_id:str) -> None:
        """
        Use this functions when sure the user is authenticated
        """
        try:
            user = u_cont.read_item(user_id, user_id)
        except CosmosResourceNotFoundError:
            return False

        self.id_ = user["id"]
        self.name = user["name"]
        self.email = user["email"]
        self.upvote = user["upvote"]
        self.downvote = user["downvote"]
        self.last_active = user["last_active"]
        self.banned = user["ban"]["status"]
        self.ban_message = user["ban"]["message"]
        self.sample_reports = user["ban"]["sample_reports"]
        self.ban_reason =  user["ban"]["reason"]
        self.ban_appeal = user["ban"]["appeal"]
        self.report_post_id = user["report"]["post_id"]
        self.report_reason = user["report"]["reason"]
        
        self.is_active = not bool(self.banned)
        self.is_authenticated = True
        self.is_anonymous = False
        self.is_broadcaster = False

        return True

    def export_user(self, u_cont):
        with open("samples/sample_user.json", "r", encoding="utf-8") as sample_user:
            user = json.load(sample_user)

        user["id"] = self.id_
        user["name"] = self.name
        user["email"] = self.email
        user["upvote"] = self.upvote
        user["downvote"] = self.downvote
        user["last_active"] = self.last_active
        user["ban"]["status"] = self.banned
        user["ban"]["message"] = self.ban_message
        user["ban"]["sample_reports"] = self.sample_reports
        user["ban"]["reason"] = self.ban_reason
        user["ban"]["appeal"] = self.ban_appeal
        user["report"]["post_id"] = self.report_post_id
        user["report"]["reason"] = self.report_reason

        u_cont.upsert_item(user)

        return True