# RSS Feed Generator for King Features

This project allows users to generate RSS feeds for the comics of their choice
at the [King Features](http://kingfeatures.com/) website (which does not
provide such feeds).

## Requirements

This is a Python 3 script which relies on the following third-party libraries:

* BeautifulSoup
* pytz
* requests
* rfeed
* slugify

## Installation

1. Clone this repo to a folder of your choice.
2. Copy the configuration file template (_rss-sources-template.json_) to a new
file named _rss-sources.json_.
3. Update the configuration file (_rss-sources.json_) to your liking (see below
for more on how to do this).
4. Set up a cron job to run the script once per day.
5. Enjoy!

## Configuration

The configuration file (_rss-sources-template.json_) has the following
components that need to be filled out. Note that this is a JSON file, so JSON
syntax is expected.

**feed_dir** (Required)  
The absolute path to a folder in which the RSS feeds themselves will live.
Example: `/home/myuser/mywebsite.com/comics`

**feed_url** (Required)  
The absolute URL that corresponds to the RSS feed directory above (internet
visible). Example: `https://mywebsite.com/comics`

**comics** (Required)  
A list of objects, each of which defines the comic to parse. Available fields
for these are listed in the corresponding section below.

**cache_dir** (Optional)  
The absoute path to a folder in which cached copies of the comic images will
live. This path should be internet visible (the feeds themselves will include
these images in them). If not provided, a `cache` folder will be created as a
subfolder of the path specified by **feed_dir**. Example:
`/home/myuser/mywebsite.com/comics/cache`

**cache_url** (Optional)  
The absolute URL that corresponds to the cache folder above (internet visible).
If not provided, a `cache` subfolder will be added to the `feed_url` value.
Example: `https://mywebsite.com/comics/cache/`

## Comics Configuration

Each entry in the `comics` configuration list can contain the following items:

**name** (Required)  
The name of the comic strip. Used to identify the feed, as well as to generate
the path to the comic strip.

**slug** (Optional)  
The slug of the comic strip. If not provided, the name field is automatically
converted into a slug (e.g. "Prince Valiant" becomes "prince-valiant").

**schedule** (Optional)  
A list of weekday names on which the comic should be loaded. If no schedule is
provided, the script will assume the comic strip is a daily, and will generate
an entry each day. Example: `"schedule": ["Sunday"]`

### Example Configurations

Here's a typical daily strip:

    {
        "name": "Sally Forth"
    }

Here's a strip that only runs on Sundays:

    {
        "name": "Prince Valiant",
        "schedule": ["Sunday"]
    }
