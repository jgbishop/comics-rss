import argparse
import calendar
import json
import os
import pytz
import rfeed

from bs4 import BeautifulSoup
from contextlib import closing
from datetime import date, datetime, timedelta
from requests import get
from requests.exceptions import RequestException
from slugify import slugify
from urllib.request import urlopen


VERSION = "1.0.0"


def get_image(url, filename):
    print(" - Attempting to get image: {}".format(filename))
    try:
        with closing(get(url, stream=True)) as resp:
            if(resp.status_code == 200):
                raw_html = resp.content
            else:
                print("ERROR: Bad response getting page ()".format(
                    resp.status_code
                ))
                return None
    except RequestException as e:
        print("ERROR: {}".format(e))
        return None

    html = BeautifulSoup(raw_html, 'lxml')
    title = html.select_one('meta[name=title]')
    short_link = html.select_one('meta[property=og:image]')

    response = urlopen(short_link['content'])
    data_response = get(response.url)
    if(data_response.status_code == 200):
        print("   Got success response code; writing image content")
        output = open(filename, "wb")
        output.write(data_response.content)
        output.close()
        return {
            'title': title
        }
    else:
        print("ERROR: Bad response downloading image ()".format(
            data_response.status_code)
        )
        return None


github_url = 'https://github.com/jgbishop/comics-rss'
root_url = "https://comicskingdom.com/"

parser = argparse.ArgumentParser()
parser.add_argument('--file', default='rss-sources.json')
args = parser.parse_args()

days = dict(zip(calendar.day_name, range(7)))

cwd = os.getcwd()
today = date.today()

# Load our config file
with open(args.file) as f:
    config = json.load(f)

# Create the cache directory
cache_dir = config.get('cache_dir', './cache')

if(cache_dir.startswith('/')):
    cache_path = cache_dir
else:
    cache_path = os.path.join(cwd, cache_dir)

os.makedirs(cache_path, exist_ok=True)

# Create the feeds directory
feed_dir = config.get('feed_dir', cwd)
os.makedirs(feed_dir, exist_ok=True)

images_processed = {}

# Process what we read from the config
for entry in config.get('comics', []):
    slug = entry.get('slug', '')
    if not slug:
        slug = slugify(entry.get('name'))

    images_processed.setdefault(slug, set())

    print("Processing comic: {}".format(slug))

    item_list = []

    last_stop = 15
    schedule = entry.get('schedule', [])
    if schedule:
        last_stop = 22  # Allow 22 days back
        schedule_weekdays = {days.get(x) for x in schedule}

    for x in range(last_stop):
        the_date = today - timedelta(days=x)

        if schedule and the_date.weekday() not in schedule_weekdays:
            continue

        img_filename = "{}-{}.gif".format(slug, the_date.isoformat())
        images_processed[slug].add(img_filename)

        url = "{}{}/{}".format(
            root_url, slug, the_date.isoformat()
        )

        # Check to see if we need to fetch the image
        img_path = os.path.join(cache_path, img_filename)
        if not os.path.isfile(img_path):
            get_image(url, img_path)

        title = "{} comic strip for {}".format(
            entry.get("name"), the_date.strftime("%B %d, %Y")
        )

        img_url = "{}{}".format(config.get("cache_url"), img_filename)
        clines = []
        clines.append('<p><img src="{}" alt="{}"></p>'.format(img_url, title))
        clines.append('<p>')
        clines.append('    <a href="{}">View on King Comics</a> -'.format(url))
        clines.append('    <a href="{}">GitHub Project</a>'.format(github_url))
        clines.append('</p>')

        pubtime = datetime.combine(the_date, datetime.min.time())
        pubtime = pubtime.replace(tzinfo=pytz.UTC)

        item = rfeed.Item(
            title=title,
            link=url,
            description='\n'.join(clines),
            author="feedgen@borngeek.com (Jonah Bishop)",
            guid=rfeed.Guid(url),
            pubDate=pubtime
        )
        item_list.append(item)

    # Start building the feed
    feed = rfeed.Feed(
        title=entry.get('name'),
        link="{}{}".format(root_url, slug),
        description="RSS feed for {}".format(entry.get('name')),
        language='en-US',
        lastBuildDate=datetime.now(),
        items=item_list
    )

    feed_path = os.path.join(feed_dir, "{}.xml".format(slug))
    with open(feed_path, "w") as feed_file:
        feed_file.write(feed.rss())

# Clean up any "expired" files from our cache directory
# items = os.listdir(cache_path)
# for x in items:
#     xpath = os.path.join(cache_path, x)

#     if not os.isfile(xpath):
#         continue  # Skip directories

#     # Only handle GIF files for now, since that's what the site creates
#     if x.endswith(".gif") and x not in images_processed:
#         os.remove(xpath)
