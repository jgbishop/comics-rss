# Core libraries
import argparse
import calendar
import glob
import json
import os
import re
import sys
from contextlib import closing
from datetime import date, datetime, timedelta
from urllib.request import urlopen

# Third-party libraries
import pytz
import rfeed
from bs4 import BeautifulSoup
from requests import get
from requests.exceptions import RequestException
from slugify import slugify


MIN_PYTHON = (3, 4)
VERSION = "1.0.0"


def get_image(url, filename):
    print(" - Attempting to get image: {}".format(filename))
    try:
        with closing(get(url, stream=True)) as resp:
            if resp.status_code == 200:
                raw_html = resp.content
            else:
                print("ERROR: Bad response getting page ({})".format(
                    resp.status_code
                ))
                return None
    except RequestException as e:
        print("ERROR: {}".format(e))
        return None

    html = BeautifulSoup(raw_html, 'lxml')
    title = html.select_one('meta[name=title]')
    short_link = html.select_one("meta[property='og:image']")

    if(not short_link):
        print("  SKIPPING: No short link found!")
        return None

    response = urlopen(short_link['content'])
    data_response = get(response.url)
    if data_response.status_code == 200:
        print("   Got success response code; writing image content")
        output = open(filename, "wb")
        output.write(data_response.content)
        output.close()
        return {
            'title': title
        }
    else:
        print("ERROR: Bad response downloading image ({})".format(
            data_response.status_code)
        )
        return None


if sys.version_info < MIN_PYTHON:
    sys.exit()

github_url = 'https://github.com/jgbishop/comics-rss'
root_url = "https://comicskingdom.com"

# Handle script arguments
parser = argparse.ArgumentParser()
parser.add_argument('--file', default='rss-sources.json')
args = parser.parse_args()

days = dict(zip(calendar.day_name, range(7)))

cwd = os.getcwd()
today = date.today()

# Load our config file
with open(args.file) as f:
    config = json.load(f)

# Make sure we have everything we expect
errors = []
for x in ('feed_dir', 'feed_url'):
    if not config.get(x, ""):
        errors.append("ERROR: Missing the {} configuration directive".format(x))
    else:
        # Strip trailing slashes from file system paths and URLs
        config[x] = config[x].rstrip('/')

if errors:
    sys.exit("\n".join(errors))

# Setup the cache paths and URLs
if not config.get('cache_dir', ''):
    config['cache_dir'] = "{}/cache".format(config['feed_dir'])
elif config.get('cache_dir').endswith('/'):
    config['cache_dir'] = config['cache_dir'].rstrip('/')

if not config.get('cache_url', ''):
    config['cache_url'] = "{}/cache".format(config['feed_url'])
elif config.get('cache_url').endswith('/'):
    config['cache_url'] = config['cache_url'].rstrip('/')

# Create the cache directory
cache_dir = config.get('cache_dir')

if not cache_dir.startswith('/'):
    cache_dir = os.path.join(cwd, cache_dir)

try:
    os.makedirs(cache_dir, exist_ok=True)
except OSError as e:
    sys.exit("Failed to create {}: {}".format(cache_dir, str(e)))

# Create the feeds directory (in case it's different)
feed_dir = config.get('feed_dir')
if not feed_dir.startswith('/'):
    feed_dir = os.path.join(cwd, feed_dir)

try:
    os.makedirs(feed_dir, exist_ok=True)
except OSError as e:
    sys.exit("Failed to create {}: {}".format(feed_dir, str(e)))

expires = config.get('expires', 0)

# Process the comics that we read from the config
images_processed = {}
for entry in config.get('comics', []):
    if not entry.get('name', ''):
        print("WARNING: Skipping comics entry with no name field")
        continue

    slug = entry.get('slug', '')
    if not slug:
        slug = slugify(entry.get('name'))

    print("Processing comic: {}".format(slug))
    images_processed.setdefault(slug, set())
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

        url = "{}/{}/{}".format(
            root_url, slug, the_date.isoformat()
        )

        # Check to see if we need to fetch the image
        img_path = os.path.join(cache_dir, img_filename)
        if not os.path.isfile(img_path):
            result = get_image(url, img_path)
            if result is None:
                continue

        title = "{} comic strip for {}".format(
            entry.get("name"), the_date.strftime("%B %d, %Y")
        )

        img_url = "{}/{}".format(config.get("cache_url"), img_filename)
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
            guid=rfeed.Guid(url),
            pubDate=pubtime
        )
        item_list.append(item)

    # Start building the feed
    feed = rfeed.Feed(
        title=entry.get('name'),
        link="{}/{}".format(root_url, slug),
        description="RSS feed for {}".format(entry.get('name')),
        language='en-US',
        lastBuildDate=datetime.now(),
        items=item_list,
        generator="comics-rss.py ({})".format(github_url),
    )

    feed_path = os.path.join(feed_dir, "{}.xml".format(slug))
    with open(feed_path, "w") as feed_file:
        feed_file.write(feed.rss())

    if(expires > 0):
        to_prune = []
        candidates = glob.glob("{}/{}-*.gif".format(cache_dir, slug))
        for img in candidates:
            if('valiant' in img):
                continue

            match = re.search(r'(\d{4}-\d{2}-\d{2})', img)
            if(match.group is None):
                print("WARNING: Unable to locate date string in file: {}".format(img))
                continue

            try:
                date = datetime.strptime(match.group(0), "%Y-%m-%d").date()
                delta = today - date
                if(delta.days >= expires):
                    to_prune.append(img)
            except ValueError:
                print("WARNING: Unable to parse date from cache file: {}".format(img))

        if(to_prune):
            print("Pruning {} expired cache files for {}.".format(len(to_prune), slug))
            for f in sorted(to_prune):
                print(" - Removing {}".format(f))
                try:
                    os.remove(f)
                except OSError:
                    raise
                    sys.exit(1)
