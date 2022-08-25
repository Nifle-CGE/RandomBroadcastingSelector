import json
import copy

class StuffImporter(object):
    def __init__(self, u_cont, _, ngettext) -> None:
        self.u_cont = u_cont
        self._ = _
        self.ngettext = ngettext
        
    def get_stats(self) -> dict:
        self.stats = self.u_cont.read_item("stats.json", "stats.json")
        return copy.deepcopy(self.stats)

    @staticmethod
    def get_config() -> dict:
        with open(f"./config.json", "r", encoding="utf-8") as json_file:
            return json.load(json_file)

    def set_stats(self, stats:dict):
        if stats != self.stats:
            self.u_cont.replace_item("stats.json", stats)
            self.stats = copy.deepcopy(stats)

    def rollback_stats(self) -> dict:
        return copy.deepcopy(self.stats)

    def pot_brods(self, last_brod:str) -> list:
        brods_query = self.u_cont.query_items(f"SELECT u.id FROM Users u WHERE NOT IS_DEFINED(u.ban) AND u.id <> '{last_brod}' AND u.id <> 'stats.json'", enable_cross_partition_query=True)
        brods = []
        while True:
            try:
                brods.append(brods_query.next()["id"])
            except StopIteration:
                break

        return brods

    def seconds_to_str(self, seconds:float) -> str:
        days = round(seconds // 86400)
        hours = round((seconds % 86400) // 3600)
        minutes = round(((seconds % 86400) % 3600) // 60)
        rem_seconds = round(((seconds % 86400) % 3600) % 60, 2)

        result = []
        if days:
            result.append(self.ngettext("%(num)s day", "%(num)s days", days))
        if hours:
            result.append(self.ngettext("%(num)s hour", "%(num)s hours", hours))
        if minutes:
            result.append(self.ngettext("%(num)s minute", "%(num)s minutes", minutes))
        if rem_seconds:
            result.append(self.ngettext("%(num)s second", "%(num)s seconds", rem_seconds))

        return ", ".join(result[:-1]) + " " + self._("and") + " " + result[-1]

    def itempaged_to_list(self, itempaged) -> list:
        result = []
        while True:
            try:
                result.append(itempaged.next())
            except StopIteration:
                return result