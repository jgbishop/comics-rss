# ruff: noqa: T201
import argparse
import calendar
import json
import re
import sys
from contextlib import closing
from datetime import date, datetime, timedelta, UTC
from http import HTTPStatus
from pathlib import Path
from zoneinfo import ZoneInfo

import rfeed
from bs4 import BeautifulSoup
from requests import get
from requests.exceptions import RequestException
from slugify import slugify


EST = ZoneInfo("America/New_York")
MIN_PYTHON = (3, 8)
VERSION = "1.1.0"


def check_target_date(date_as_string):
    today = datetime.now(tz=EST).date()

    try:
        target_date = datetime.strptime(date_as_string, "%Y-%m-%d").astimezone(EST).date()
        if target_date != today:
            print(f"Target date does not match expected date: {target_date} vs {today}")
            return False

        return True
    except ValueError:
        print(f"Unable to locate date in comics page URL: {url}")
        return False


def get_image(url, filename):
    """
    Obtains the requested image.

    Args
        url: The URL to the comics webpage that we need to parse
        filename: The filename we will write the resulting image to
    """

    match = re.search(r'(\d{4}-\d{2}-\d{2})', url)
    if not match.group:
        print(f"Unexpected comics page URL: {url}")
        return None

    if not check_target_date(match.group(0)):
        return None

    print(f" - Scraping comic URL: {url}")
    try:
        with closing(get(url, stream=True, timeout=15)) as resp:
            if resp.status_code == HTTPStatus.OK:
                raw_html = resp.content
            else:
                print(f"ERROR: Bad response getting page ({resp.status_code})")
                return None
    except RequestException as e:
        print(str(e))
        return None

    html = BeautifulSoup(raw_html, 'html.parser')
    title = html.select_one('meta[name=title]')
    short_link = html.find('meta', attrs={'property': 'og:image'})

    final_img_url = short_link['content']
    if not final_img_url.startswith(("http:", "https:")):
        print(f"Bad image URL ({final_img_url})")
        return None

    match = re.search(r'(\d{4}-\d{2}-\d{2})', final_img_url)
    if not check_target_date(match.group(0)):
        return None

    print(f"   Accessing image URL: {final_img_url}")
    data_response = get(final_img_url, timeout=15)
    if data_response.status_code != HTTPStatus.OK:
        print(f"ERROR: Bad response downloading image ({data_response.status_code})")
        return None

    print("   Got success response code; writing image content")
    with filename.open("wb") as file:
        file.write(data_response.content)

    return {'title': title}


if sys.version_info < MIN_PYTHON:
    sys.exit()

github_url = 'https://github.com/jgbishop/comics-rss'
root_url = "https://comicskingdom.com"

# Handle script arguments
parser = argparse.ArgumentParser()
parser.add_argument('--file', default='rss-sources.json')
args = parser.parse_args()

days = dict(zip(calendar.day_name, range(7), strict=True))

cwd = Path.cwd()
today = datetime.now(tz=EST).date()

# Load our config file
with Path(args.file).open(encoding='utf-8') as f:
    config = json.load(f)

# Make sure we have everything we expect
errors = []
for x in ('feed_dir', 'feed_url'):
    if not config.get(x):
        errors.append(f"ERROR: Missing the {x} configuration directive")
    else:
        # Strip trailing slashes from file system paths and URLs
        config[x] = config[x].rstrip('/')

if errors:
    sys.exit('\n'.join(errors))

# Setup the cache paths and URLs
if not config.get('cache_dir', ''):
    config['cache_dir'] = f"{config['feed_dir']}/cache"
elif config.get('cache_dir').endswith('/'):
    config['cache_dir'] = config['cache_dir'].rstrip('/')

if not config.get('cache_url', ''):
    config['cache_url'] = f"{config['feed_url']}/cache"
elif config.get('cache_url').endswith('/'):
    config['cache_url'] = config['cache_url'].rstrip('/')

# Create the cache directory
raw_cache_dir = config.get('cache_dir')
cache_dir = Path(raw_cache_dir) if raw_cache_dir.startswith('/') else cwd.joinpath(raw_cache_dir)

try:
    cache_dir.mkdir(exist_ok=True, parents=True)
except OSError as e:
    sys.exit(f"Failed to create {cache_dir}: {e}")

# Create the feeds directory (in case it's different)
raw_feed_dir = config.get('feed_dir')
feed_dir = Path(raw_feed_dir) if raw_feed_dir.startswith('/') else cwd.joinpath(raw_feed_dir)

try:
    feed_dir.mkdir(exist_ok=True, parents=True)
except OSError as e:
    sys.exit(f"Failed to create {feed_dir}: {e}")

expires = config.get('expires', 0)

# Process the comics that we read from the config
images_processed = {}
for entry in config.get('comics', []):
    if not entry.get('name', ''):
        print("WARNING: Skipping comics entry with no name field")
        continue

    slug = entry.get('slug', '') or slugify(entry.get('name'))

    print(f"Processing comic: {slug}")
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

        img_filename = f"{slug}-{the_date.isoformat()}.jpeg"
        images_processed[slug].add(img_filename)

        url = f"{root_url}/{slug}/{the_date.isoformat()}"

        # Check to see if we need to fetch the image
        img_path = cache_dir.joinpath(img_filename)
        if not img_path.is_file():
            get_image(url, img_path)

        title = f"{entry.get('name')} comic strip for {the_date.strftime('%B %d, %Y')}"

        img_url = f"{config.get('cache_url')}/{img_filename}"
        clines = [
            f'<p><img src="{img_url}" alt="{title}"></p>',
            '<p>',
            f'    <a href="{url}">View on King Comics</a> - ',
            f'    <a href="{github_url}">Generated by comics-rss on GitHub</a>',
            '</p>',
        ]

        pubtime = datetime.combine(the_date, datetime.min.time())
        pubtime = pubtime.replace(tzinfo=UTC)

        item = rfeed.Item(title=title, link=url, description='\n'.join(clines),
                          guid=rfeed.Guid(url), pubDate=pubtime)
        item_list.append(item)

    # Start building the feed
    feed = rfeed.Feed(
        title=entry.get('name'),
        link=f"{root_url}/{slug}",
        description=f"RSS feed for {entry.get('name')}",
        language='en-US',
        lastBuildDate=datetime.now(tz=EST),
        items=item_list,
        generator=f"comics-rss.py ({github_url})",
    )

    feed_path = feed_dir.joinpath(f'{slug}.xml')
    with feed_path.open('w') as feed_file:
        feed_file.write(feed.rss())

    if expires > 0:
        to_prune = []
        candidates = cache_dir.glob(f"{slug}-*.jpeg")
        for img in candidates:
            match = re.search(r'(\d{4}-\d{2}-\d{2})', str(img))
            if match.group is None:
                print(f"WARNING: Unable to locate date string in file: {img}")
                continue

            try:
                date = datetime.strptime(match.group(0), "%Y-%m-%d").astimezone(EST).date()
                delta = today - date
                if delta.days >= expires:
                    to_prune.append(img)
            except ValueError:
                print(f"WARNING: Unable to parse date from cache file: {img}")

        if to_prune:
            print(f"Pruning {len(to_prune)} expired cache file(s) for {slug}.")
            for f in sorted(to_prune):
                print(f" - Removing {f}")
                try:
                    f.unlink(missing_ok=True)
                except OSError as e:
                    sys.exit(str(e))
