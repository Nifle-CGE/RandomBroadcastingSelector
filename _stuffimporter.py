import json

def get_json(filename):
    with open(f"./{filename}.json", "r", encoding="utf-8") as json_file:
        return json.load(json_file)

def set_stats(stats:dict):
    with open(f"./stats.json", "w", encoding="utf-8") as stats_file:
        json.dump(stats, stats_file, indent=4)

def pot_brods(u_cont, last_brod:str):
    brods_query = u_cont.query_items(f"SELECT u.id FROM Users u WHERE NOT IS_DEFINED(u.ban) AND u.id <> '{last_brod}'", enable_cross_partition_query=True)
    brods = []
    while True:
        try:
            brods.append(brods_query.next()["id"])
        except StopIteration:
            break

    return brods

def seconds_to_str(seconds:float):
    days = round(seconds // 86400)
    hours = round((seconds % 86400) // 3600)
    minutes = round(((seconds % 86400) % 3600) // 60)
    rem_seconds = round(((seconds % 86400) % 3600) % 60, 2)

    result = []
    if days:
        result.append(f"{days} days")
    if hours:
        result.append(f"{hours} hours")
    if minutes:
        result.append(f"{minutes} minutes")
    if rem_seconds:
        result.append(f"{rem_seconds} seconds")

    return " ".join(result)

def itempaged_to_list(itempaged) -> list:
    result = []
    while True:
        try:
            result.append(itempaged.next())
        except StopIteration:
            return result