import requests
import re
from diskcache import Cache

cache = Cache("cache")

def poll_for_reddit_codes(cache):

    headers = {
        "User-Agent": "GanyuBot"
    }

    QUERY_URL = "https://www.reddit.com/r/Genshin_Impact/search.json?q=code&restrict_sr=1&t=day"
    TEST_URL = "https://www.reddit.com/r/Genshin_Impact/search.json?q=code&restrict_sr=1&t=week"
    res = requests.get(TEST_URL, headers=headers)
    search_data = res.json()

    code_regex = re.compile(r' *[A-Z0-9]{12} *')
    code_link_regex = re.compile(r' *https:\/\/genshin\.hoyoverse\.com\/en\/gift\?code=[A-Z0-9]{12} *')
    code_keyword_regex = re.compile(r'(\w+ )?codes?', re.IGNORECASE)

    codes = set()
    for post in search_data['data']['children']:
        title = post['data']['title']
        body = post['data']['selftext']
        id = post['data']['id']
        cache_key = f"reddit_{id}"
        if cache_key in cache:
            continue
        
        if code_regex.search(title + "\n" + body) or code_keyword_regex.search(title + "\n" + body) or code_link_regex.search(title + "\n" + body):
            raw_codes = code_regex.findall(title + "\n" + body)
            code_links = code_link_regex.findall(title + "\n" + body)
            comment_codes = []
            # search comments
            post_url = f"https://www.reddit.com{post['data']['permalink'][:-1]}.json"
            post_res = requests.get(post_url, headers=headers)
            post_data = post_res.json()
            if len(post_data) > 1:
                comments = post_data[1]
                for comment in comments['data']['children']:
                    comment_body = comment['data'].get("body", "")
                    comment_codes = code_regex.findall(comment_body) + code_link_regex.findall(comment_body)

            # add codes from title, body, and comments
            for code in list(dict.fromkeys(raw_codes + code_links + comment_codes)):
                code = code.strip()[-12:]
                if f"code_{code}" not in cache:
                    codes.add(code)
                    cache.set(f"code_{code}", code, expire=3600)
            
          
        # cache.set(cache_key, cache_key, expire=3600)  # 24 hr cache

        print(post['data']['title'])
    print(codes)

poll_for_reddit_codes(cache)