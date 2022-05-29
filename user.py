from azure.cosmos.exceptions import *
import json

class User:
    def __init__(self, id_=None, name=None, email=None, lang="en") -> None:
        self.id_ = id_
        self.name = name
        self.email = email
        self.message_score = 0
        self.last_logged_in = 0
        self.lang = lang
        self.banned = 0
        self.ban_message = ""
        self.sample_reports = [] 
        self.ban_reason =  ""
        self.ban_appeal = ""
        self.report_timestamp = 0
        self.report_reason = ""
        self.is_active = True
        self.is_authenticated = True

    def get_id(self):
        return self.id_

    def import_user(self, u_cont, user_id:str):
        try:
            user = u_cont.read_item(user_id, user_id)
        except CosmosResourceNotFoundError:
            return False

        self.id_ = user["id"]
        self.name = user["name"]
        self.email = user["email"]
        self.message_score = user["message_score"]
        self.last_logged_in = user["last_logged_in"]
        self.lang = user["lang"]
        self.banned = user["ban"]["status"]
        self.ban_message = user["ban"]["message"]
        self.sample_reports = user["ban"]["sample_reports"]
        self.ban_reason =  user["ban"]["reason"]
        self.ban_appeal = user["ban"]["appeal"]
        self.report_timestamp = user["report"]["timestamp"]
        self.report_reason = user["report"]["reason"]
        
        self.is_active = not bool(self.banned)
        self.is_authenticated = True
        self.is_anonymous = False

        return True

    def export_user(self, u_cont):
        with open("samples/sample_user.json", "r", encoding="utf-8") as sample_user:
            user = json.load(sample_user)

        user["id"] = self.id_
        user["name"] = self.name
        user["email"] = self.email
        user["message_score"] = self.message_score
        user["last_logged_in"] = self.last_logged_in
        user["lang"] = self.lang
        user["ban"]["status"] = self.banned
        user["ban"]["message"] = self.ban_message
        user["ban"]["sample_reports"] = self.sample_reports
        user["ban"]["reason"] = self.ban_reason
        user["ban"]["appeal"] = self.ban_appeal
        user["report"]["timestamp"] = self.report_timestamp
        user["report"]["reason"] = self.report_reason

        u_cont.upsert_item(user)

        return True