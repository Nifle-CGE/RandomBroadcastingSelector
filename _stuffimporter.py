import json

def get_json(filename):
    with open(f"./{filename}.json", "r", encoding="utf-8") as json_file:
        return json.load(json_file)

def set_stats(dict_:dict):
    with open(f"./stats.json", "w", encoding="utf-8") as stats_file:
        json.dump(dict_, stats_file)

def pot_brods(u_cont):
    brods_query = u_cont.query_items("SELECT u.id FROM Users u WHERE u.no.brod = 0 AND u.ban.status = 0 AND u.id <> " + get_json("config")["broadcaster"], enable_cross_partition_query=True)
    brods = []
    while True:
        try:
            brods.append(int(brods_query.next()["id"]))
        except StopIteration:
            break

    return brods

def seconds_to_str(seconds:float):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = ((seconds % 86400) % 3600) // 60
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