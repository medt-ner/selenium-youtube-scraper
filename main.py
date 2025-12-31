import json
import sqlite3
import time
import argparse
import logging

import selenium.webdriver.remote.webelement
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common import StaleElementReferenceException
from selenium.webdriver.common.by import By

from selenium.webdriver.firefox.options import Options

from urllib.parse import urlparse, parse_qs

ff_options = Options()
ff_options.page_load_strategy = 'eager'
# ff_options.add_argument('--headless')

driver1 = webdriver.Firefox(options=ff_options)
driver1.delete_all_cookies()

with open('config.json', 'r') as files:
    config = json.load(files)

# optionally use ublock origin
driver1.install_addon(path=config["ublock-origin-path"])
# just comment this out if you need to

conn = sqlite3.connect("ytv.db")
crsr = conn.cursor()

channel_table_creation_command = """CREATE TABLE IF NOT EXISTS channel (
channelID CHAR(24) PRIMARY KEY,
name TEXT,
handle TEXT
);"""

video_table_creation_command = """CREATE TABLE IF NOT EXISTS video (
videoID CHAR(11) PRIMARY KEY,
channelID CHAR(24),
title TEXT,
scraped BOOL,
transcript BOOL,
FOREIGN KEY (channelID) REFERENCES channel(channelID) ON DELETE CASCADE
);"""

# I have no idea how large a transcript snippet's text can be.
# I pasted in probably 100k 3 byte characters, and it let me save the video transcript.
snippet_table_creation_command = """CREATE TABLE IF NOT EXISTS snippet (
videoID CHAR(11),
channelID CHAR(24),
text TEXT,
seconds_start_time INTEGER, 
start_time TEXT,
PRIMARY KEY (videoID, text, start_time),
FOREIGN KEY (videoID) REFERENCES video(videoID) ON DELETE CASCADE,
FOREIGN KEY (channelID) REFERENCES channel(channelID) ON DELETE CASCADE
);"""

comment_table_creation_command = """CREATE TABLE IF NOT EXISTS comment (
commentID TEXT,
parentID TEXT,
videochannelID CHAR(24),
videoID CHAR(11),
text TEXT,
user_handle TEXT,
likes INTEGER,
creator_heart BOOL,
PRIMARY KEY (commentID),
FOREIGN KEY (parentID) REFERENCES comment(commentID) ON DELETE CASCADE,
FOREIGN KEY (videochannelID) REFERENCES channel(channelID) ON DELETE CASCADE,
FOREIGN KEY (videoID) REFERENCES video(videoID) ON DELETE CASCADE
);"""

conn.execute(channel_table_creation_command)
conn.execute(video_table_creation_command)
conn.execute(snippet_table_creation_command)
conn.execute(comment_table_creation_command)


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def scroll_and_click(driver, el):
    """
    Scrolls driver to the element 'el' and clicks on it.
    """
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            el
        )
        driver.execute_script("""
                        const el = arguments[0];
                        el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
                    """, el)
        return True
    except StaleElementReferenceException:
        return False


def get_video_id(video_link):
    if video_link.endswith("/"): video_link = video_link[:-1]
    if "&" in video_link: video_link, unimportant = video_link.split("&", 1)
    if len(video_link) == 11: return video_link
    if "/shorts/" in video_link:
        unimportant, vid_id = video_link.rsplit("/", 1)
    else:
        unimportant, vid_id = video_link.split("ch?v=", 1)
    return vid_id


def channel_parser(driver, channel_link):
    channel_video_type_parser(driver, channel_link, "/videos")
    channel_video_type_parser(driver, channel_link, "/streams")


def channel_video_type_parser(driver, channel_link, ctype):
    if ctype not in channel_link:
        if channel_link.endswith("/"): channel_link = channel_link[:-1]
        channel_link = f"{channel_link}{ctype}"

    driver.get(channel_link)

    time.sleep(3)

    page_source = driver.page_source
    channel_id_obj = driver.find_element(By.XPATH, "//link[starts-with(@href, 'https://www.youtube.com/channel/')]")

    channel_id = channel_id_obj.get_attribute('href')
    channel_id = channel_id.strip().replace("https://www.youtube.com/channel/", "")

    if ctype == "/videos":

        # find video count
        about_button = driver.find_element(By.XPATH,
                                           "/html/body/ytd-app/div[1]/ytd-page-manager/ytd-browse/div["
                                           "4]/ytd-tabbed-page-header/tp-yt-app-header-layout/div/tp-yt-app-header"
                                           "/div["
                                           "2]/div/div/yt-page-header-renderer/yt-page-header-view-model/div/div["
                                           "1]/div/yt-description-preview-view-model/truncated-text/button/span")
        about_button.click()
        time.sleep(5)

        page_source = driver.page_source

        additional_info = driver.find_element(By.XPATH, "//div[@id='additional-info-container' and contains(@class, "
                                                        "'about-section')]")
        video_count = additional_info.find_element(By.XPATH, "//td[contains(text(), 'video') and not(contains(text(),"
                                                             "'youtube'))]")
        video_count = video_count.text.replace(",", "").strip()
        print(f"This channel has {video_count}.")
        video_count, trash = video_count.split(" ", 1)

        print(f"Channel id: {channel_id}")
        try:
            channel_handle_obj = driver.find_element(By.XPATH, "//link[starts-with(@href, 'https://m.youtube.com/@')]")
            channel_handle = channel_handle_obj.get_attribute('href')
            channel_handle = channel_handle.replace("https://m.youtube.com/@", "").replace("/videos", "").strip()
        except:
            channel_handle_obj = driver.find_element(By.XPATH,
                                                     "//link[starts-with(@href, 'https://m.youtube.com/channel/')]")
            channel_handle = channel_handle_obj.get_attribute('href')
            channel_handle = channel_handle.replace("https://m.youtube.com/channel/", "").replace("/videos", "").strip()

        print(f"Channel handle: {channel_handle}")
        channel_name_obj = driver.find_element(By.XPATH, "//link[@itemprop='name']")
        channel_name = channel_name_obj.get_attribute('content')
        print(f"Channel name: {channel_name}")
        close_button = driver.find_element(By.XPATH,
                                           "//button[contains(@aria-label, 'Close') and contains(@class, "
                                           "'yt-spec-button-shape-next yt-spec-button-shape-next--text "
                                           "yt-spec-button-shape-next--mono yt-spec-button-shape-next--size-m')]")
        close_button.click()

        # <link itemprop="name" content="The Ultimate Classical Music Guide by Dave Hurwitz">
        crsr.execute("INSERT OR REPLACE INTO channel (channelID, name, handle) VALUES (?, ?, ?)",
                     (channel_id, channel_name, channel_handle))

    # Parse the page source with BeautifulSoup
    soup = BeautifulSoup(page_source, 'html.parser')

    content_container = soup.find_all('a', id="thumbnail")
    initial_content = len(content_container)

    iteration_count = 1
    curr_length = 0
    prev_height = driver.execute_script("return document.documentElement.scrollHeight")  # Initial page height
    last_check_time = time.time()

    while True:
        # Scroll down continuously
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(2)  # Short pause to allow content to load

        # Check every 60 seconds if page height has increased
        if time.time() - last_check_time >= 11:
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            if new_height > prev_height:
                prev_height = new_height  # Update stored height
            else:
                break
            last_check_time = time.time()

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    content_containers = soup.find_all('a', id="video-title-link")
    print(len(content_containers))

    for x in content_containers:
        if not x: continue
        try:
            vid_part = x['href'].replace("/watch?v=", "")
            vid_part = vid_part[:11]
            if "?pp" in vid_part: print("found playlist video")
            if vid_part == 'src':
                print(thumb)
            elif not vid_part:
                print(thumb)
            title = x['title']
            print(f"Saving {title} https://www.youtube.com/watch?v={vid_part}")
            crsr.execute("INSERT OR IGNORE INTO video (videoID, channelID, title, scraped, transcript) VALUES (?, ?, "
                         "?, ?, ?)",
                         (vid_part, channel_id, title, False, True))
        except Exception as e:
            print(e)

    conn.commit()

    # Parse the page source with BeautifulSoup
    soup = BeautifulSoup(page_source, 'html.parser')

    content_container = soup.find_all('a', id="thumbnail")
    initial_content = len(content_container)

    prev_height = driver.execute_script("return document.documentElement.scrollHeight")  # Initial page height
    last_check_time = time.time()
    while True:
        # Scroll down continuously
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(2)  # Short pause to allow content to load

        # Check every 60 seconds if page height has increased
        if time.time() - last_check_time >= 11:
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            if new_height > prev_height:
                prev_height = new_height  # Update stored height
            else:
                break
            last_check_time = time.time()
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    content_containers = soup.find_all('a', id="video-title-link")
    print(len(content_containers))

    for x in content_containers:
        if not x: continue
        try:
            vid_part = x['href'].replace("/watch?v=", "")
            vid_part = vid_part[:11]
            if "?pp" in vid_part: print("found playlist video")
            if vid_part == 'src':
                print(thumb)
            elif not vid_part:
                print(thumb)
            title = x['title']
            print(f"Saving {title} https://www.youtube.com/watch?v={vid_part}")
            crsr.execute("INSERT OR IGNORE INTO video (videoID, channelID, title) VALUES (?, ?, ?)",
                         (vid_part, channel_id, title))
        except Exception as e:
            print(e)
    conn.commit()


def query_parser(driver, query_link, depth: int):

    goal_int = depth
    driver.get(query_link)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
    content_container = []
    count = 0
    while True:
        print(f"Iterating {len(content_container)}")

        # driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(5)
        page_source = driver.page_source

        # Parse the page source with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')

        content_container = soup.find_all('ytd-video-renderer', class_="style-scope ytd-item-section-renderer")

        # look for video titles, links, author
        # pre-installing ublock filters would be helpful

        current_content = len(content_container)
        if current_content >= goal_int and count > 0: break
        count += 1

    results = driver.find_elements(By.XPATH, "//ytd-video-renderer")
    first = True
    videos = []
    for x in results:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            x
        )
        if first:
            time.sleep(2)
            first = False
        else: time.sleep(0.08)
        # title = x.find("a", id="video-title")
        title = x.find_element(By.XPATH, ".//a[@id='video-title']")
        print(title.text.strip())

        # thumbnail = x.find("a", id="thumbnail")
        thumbnail = x.find_element(By.XPATH, ".//a[@id='thumbnail']")
        print(thumbnail.get_attribute("href"))
        videos.append(get_video_id(thumbnail.get_attribute("href")))

    for x in videos:
        video_parser(driver, x)


def parse_comment(comment: selenium.webdriver.remote.webelement.WebElement, videoID: str, videoChannelID: str = None):
    # Locating comment ID
    curr_comment = comment.find_element(By.XPATH, ".//span[contains(@id, 'published-time-text')]")
    curre_comment = curr_comment.find_element(By.XPATH,
                                              ".//a[contains(@class, 'yt-simple-endpoint style-scope "
                                              "ytd-comment-view-model')]")
    href = curre_comment.get_attribute('href')

    if not href:
        print(comment)
        print("No href in comment?")
        quit()
    if "lc=" not in href:
        print("wacky comment href")
        print(href)
        quit()

    trash, href = href.rsplit("lc=", 1)
    if "&pp=" in href:
        href, trash = href.rsplit("&pp=", 1)
    parentID = None
    if "." in href:
        parentID, commentID = href.rsplit(".", 1)
    else:
        commentID = href

    # Locating commenter handle
    curr_comment = comment.find_element(By.XPATH, ".//a[contains(@id, 'author-text') and contains(@class, "
                                                  "'yt-simple-endpoint style-scope ytd-comment-view-model')]")
    href = curr_comment.get_attribute('href')
    try:
        if "/@" in href:
            trash, handle = href.rsplit("/@")
        elif "/user/" in href:
            trash, handle = href.rsplit("user/")
        else:
            trash, handle = href.rsplit("channel/", 1)
    except Exception as e:
        print(f"href: {href}\n Exception: {e}")
        quit()

    # Locating comment text
    curr_comment = comment.find_element(By.XPATH, ".//span[contains(@class, 'yt-core-attributed-string "
                                                  "yt-core-attributed-string--white-space-pre-wrap')]")
    comment_text = curr_comment.text

    # Locating comment likes
    curr_comment = comment.find_element(By.XPATH, ".//span[contains(@id, 'vote-count-middle') and contains(@class, "
                                                  "'style-scope ytd-comment-engagement-bar')]")
    comment_likes = curr_comment.text.strip()
    if comment_likes == '':
        comment_likes = 0
    else:
        if "k" in comment_likes.lower():
            comment_likes = int(float(comment_likes.replace("K", "")) * 1000)
        elif "m" in comment_likes.lower():
            comment_likes = int(float(comment_likes.replace("M", "")) * 1000000)
        else:
            comment_likes = int(comment_likes)

    # Locating Creator heart
    creator_heart_div = comment.find_element(By.XPATH,
                                             ".//div[contains(@id, 'creator-heart') and contains(@class, 'style-scope "
                                             "ytd-comment-engagement-bar')]")
    inner_html = creator_heart_div.get_attribute("innerHTML").strip()
    creator_heart = False
    if inner_html: creator_heart = True
    print(commentID, parentID, comment_text, handle, comment_likes, creator_heart)
    crsr.execute(
        "INSERT OR REPLACE INTO comment (commentID, parentID, videochannelID, videoID, text, user_handle, likes, "
        "creator_heart) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (commentID, parentID, videoChannelID, videoID, comment_text, handle, comment_likes, creator_heart))
    conn.commit()
    return commentID


def playlist_parser(driver, playlist_link):
    try:
        driver.get(playlist_link)
        time.sleep(1)
        page_source = driver.page_source

        # Parse the page source with BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')

        content_container = soup.find_all('a', id="thumbnail")
        initial_content = len(content_container)
        count = 0

        while True:
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
            time.sleep(5)
            page_source = driver.page_source

            # Parse the page source with BeautifulSoup
            soup = BeautifulSoup(page_source, 'html.parser')

            content_container = soup.find_all('a', id="thumbnail")
            current_content = len(content_container)
            if current_content == initial_content and count > 0: break
            initial_content = current_content
            count += 1

        for x in content_container:
            if 'href' not in x: continue
            link = x['href']
            if len(link) < 11: continue
            video_parser(driver, video_link=get_video_id(link))

    except Exception as e:
        print(e)


def comment_parser(driver, video_link):
    videoID = get_video_id(video_link)
    video_link = f"https://www.youtube.com/watch?v={videoID}"
    driver.get(video_link)
    driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")

    prev_height = driver.execute_script("return document.documentElement.scrollHeight")  # Initial page height
    last_check_time = time.time()
    time.sleep(3)
    video_block = driver.find_element(By.XPATH, "//div[@id='player']")
    driver.execute_script("arguments[0].remove();", video_block)
    time.sleep(3)
    try:
        sort_by_box = driver.find_element(By.CSS_SELECTOR,
                                          "yt-sort-filter-sub-menu-renderer.ytd-comments-header-renderer > yt-dropdown-menu:nth-child(2) > tp-yt-paper-menu-button:nth-child(1) > div:nth-child(1) > tp-yt-paper-button:nth-child(1)")
    except selenium.common.exceptions.NoSuchElementException:
        time.sleep(5)

        sort_by_box = driver.find_element(By.CSS_SELECTOR,
                                          "yt-sort-filter-sub-menu-renderer.ytd-comments-header-renderer > yt-dropdown-menu:nth-child(2) > tp-yt-paper-menu-button:nth-child(1) > div:nth-child(1) > tp-yt-paper-button:nth-child(1)")

    suggested_videos = driver.find_element(By.XPATH, "//div[@id='secondary-inner' and @class='style-scope "
                                                     "ytd-watch-flexy']")

    scroll_and_click(driver, sort_by_box)
    time.sleep(3)
    sort_by_new_option = driver.find_element(By.CSS_SELECTOR, "yt-sort-filter-sub-menu-renderer.ytd-comments-header-renderer > yt-dropdown-menu:nth-child(2) > tp-yt-paper-menu-button:nth-child(1) > tp-yt-iron-dropdown:nth-child(2) > div:nth-child(1) > div:nth-child(1) > tp-yt-paper-listbox:nth-child(1) > a:nth-child(2) > tp-yt-paper-item:nth-child(1)")
    scroll_and_click(driver, sort_by_new_option)
    time.sleep(3)
    driver.execute_script("arguments[0].remove();", suggested_videos)
    while True:

        def spinnerwait():
            while True:
                time.sleep(1)
                # spinners = driver.find_elements(By.XPATH, "//tp-yt-paper-spinner[@id='spinner']")
                spinners = driver.find_elements(By.XPATH, "//tp-yt-paper-spinner[@id='spinner']")
                visible_spinners = []

                for spinner in spinners:
                    try:
                        aria_hidden = spinner.get_attribute("aria-hidden")
                        aria_label = spinner.get_attribute("aria-label")
                    except StaleElementReferenceException:
                        continue

                    if aria_hidden == "true" or aria_label == "loading": continue

                    visible_spinners.append(spinner)

                # print(spinners[0].get_attribute('outerHTML'))
                print(f"waiting on spinners {len(spinners)}")
                if len(visible_spinners) == 0: break

        e_button_count = 1
        m_button_count = 1

        spinnerwait()

        def process_buttons(buttons: list):
            good_buttons = []
            for button in buttons:
                if not button.is_displayed(): continue
                good_buttons.append(button)
                # print(button.get_attribute('outerHTML'))
                scroll_and_click(driver=driver, el=button)
                driver.execute_script("arguments[0].remove();", button)
            return good_buttons

        # Loading comment replies loop
        while e_button_count > 0 or m_button_count > 0:
            expand_buttons = driver.find_elements(By.XPATH, "//ytd-button-renderer[@id='more-replies-sub-thread']")
            actual_expand_buttons = process_buttons(expand_buttons)

            # expand the comment replies button
            # ytd-button-renderer
            more_expand_buttons = driver.find_elements(By.CSS_SELECTOR,
                                                       "ytd-continuation-item-renderer.replies-continuation button[aria-label='Show more replies']")
            actual_more_expand_buttons = process_buttons(more_expand_buttons)

            e_button_count = len(actual_expand_buttons)
            m_button_count = len(actual_more_expand_buttons)

            if e_button_count != 0 or m_button_count != 0:
                spinnerwait()

        # Scroll down continuously
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
        print("Scrolling down.")
        spinnerwait()

        # Check every 60 seconds if page height has increased
        if e_button_count == 0 and m_button_count == 0: print("No extra comment buttons found")
        if time.time() - last_check_time >= 15:
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            print(f"{new_height} != {prev_height} and {e_button_count} != 0 and {m_button_count}")
            if (new_height > prev_height) or (e_button_count != 0 and m_button_count != 0):
                prev_height = new_height  # Update stored height
            else:
                # print(f"{new_height} {prev_height}")
                break
            last_check_time = time.time()

    comments = driver.find_elements(By.XPATH,
                                    "//div[@id='body' and contains(@class, 'style-scope ytd-comment-view-model')]")
    print(f"Found {len(comments)} comments")
    comment_ids = set()
    for x in comments:
        result = parse_comment(x, videoID)
        if result: comment_ids.add(result)

    print(f"Better estimate of comments: {len(comment_ids)}")
    crsr.execute("UPDATE video SET scraped = 1 - scraped WHERE videoID = ?", (videoID,))
    conn.commit()


def video_parser(driver, video_link, channelID: str = None, comments: bool = False):
    videoID = get_video_id(video_link)
    video_link = f"https://www.youtube.com/watch?v={videoID}"
    driver.get(video_link)
    driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")

    # no channel id for commenter in html?
    time.sleep(3)
    prev_height = driver.execute_script("return document.documentElement.scrollHeight")  # Initial page height
    last_check_time = time.time()
    time.sleep(2.5)

    # remove pop-up
    try:
        popup = driver.find_element(By.XPATH, "//div[contains(@class, 'yt-mealbar-promo-renderer-logo-with-padding')]")
        driver.execute_script("arguments[0].remove();", popup)
    except Exception as e:
        time.sleep(0.1)

    # get transcript

    # attempts to close pop-up tabs
    if "https://www.youtube" not in driver.current_url: driver.close()
    description_button = driver.find_element(By.XPATH, "//tp-yt-paper-button[@id='expand' and contains(@class, "
                                                       "'ytd-text-inline-expander')]")
    description_button.click()
    time.sleep(1)
    try:
        open_transcript_button = driver.find_element(By.XPATH, "/html/body/ytd-app/div["
                                                               "1]/ytd-page-manager/ytd-watch-flexy/div[5]/div["
                                                               "1]/div/div[2]/ytd-watch-metadata/div/div[4]/div["
                                                               "1]/div/ytd-text-inline-expander/div["
                                                               "3]/ytd-structured-description-content-renderer/div["
                                                               "3]/ytd-video-description-transcript-section-renderer/div["
                                                               "3]/div/ytd-button-renderer/yt-button-shape/button")
        open_transcript_button.click()
    except Exception as e:
        print(f"Failed on/no transcript for {videoID}")
        crsr.execute("UPDATE video SET scraped = 1 WHERE videoID =?;", (videoID,))
        crsr.execute("UPDATE video SET transcript = 0 WHERE videoID =?;", (videoID,))
        conn.commit()

    time.sleep(5)

    page_source = driver.page_source
    soup = BeautifulSoup(page_source, 'html.parser')
    segment_containers = soup.find_all('ytd-transcript-segment-renderer', class_="ytd-transcript-segment-list-renderer")
    if len(segment_containers) == 0:
        print("No transcript, attempting to load again.")
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
        driver.execute_script("return document.documentElement.scrollHeight")

        time.sleep(3)
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        segment_containers = soup.find_all('ytd-transcript-segment-renderer',
                                           class_="ytd-transcript-segment-list-renderer")
        if len(segment_containers) == 0:
            print("No transcript was loaded.")

    for x in segment_containers:

        # ---- snippet timestamp ----
        timestamp_text = x.find('div', class_="segment-timestamp style-scope ytd-transcript-segment-renderer")
        timestamp_text = timestamp_text.text
        timestamp_text = timestamp_text.replace(",", "")  # sometimes there's a comma in a timestamp: 0nZAHgPhY7U
        colon_count = timestamp_text.count(":")

        days = 0
        hours = 0
        minutes = 0
        seconds = 0

        if colon_count == 3:
            days, hours, minutes, seconds = timestamp_text.split(":", 3)
        if colon_count == 2:
            hours, minutes, seconds = timestamp_text.split(":", 2)
        if colon_count == 1:
            minutes, seconds = timestamp_text.split(":", 1)
        if days: days = int(days)
        if hours: hours = int(hours)
        if minutes: minutes = int(minutes)
        if seconds: seconds = int(seconds)

        seconds_start_time = seconds + (minutes * 60) + (hours * 60 * 60) + (days * 24 * 60 * 60)

        # ---- snippet text ----
        snippet_text = x.find('yt-formatted-string', class_="segment-text style-scope ytd-transcript-segment-renderer")
        snippet_text = snippet_text.text

        crsr.execute(
            "INSERT OR REPLACE INTO snippet (videoID, channelID, text, seconds_start_time, start_time) VALUES (?, ?, ?, ?, ?)",
            (videoID, channelID, snippet_text, seconds_start_time, timestamp_text))

    conn.commit()

    # -------  Comment Scraping  ------- #

    if not comments: return

    prev_height = driver.execute_script("return document.documentElement.scrollHeight")  # Initial page height
    last_check_time = time.time()
    time.sleep(3)
    video_block = driver.find_element(By.XPATH, "//div[@id='player']")
    driver.execute_script("arguments[0].remove();", video_block)
    time.sleep(3)
    try:
        sort_by_box = driver.find_element(By.CSS_SELECTOR,
                                          "yt-sort-filter-sub-menu-renderer.ytd-comments-header-renderer > yt-dropdown-menu:nth-child(2) > tp-yt-paper-menu-button:nth-child(1) > div:nth-child(1) > tp-yt-paper-button:nth-child(1)")
    except selenium.common.exceptions.NoSuchElementException:
        time.sleep(5)

        sort_by_box = driver.find_element(By.CSS_SELECTOR,
                                          "yt-sort-filter-sub-menu-renderer.ytd-comments-header-renderer > yt-dropdown-menu:nth-child(2) > tp-yt-paper-menu-button:nth-child(1) > div:nth-child(1) > tp-yt-paper-button:nth-child(1)")

    suggested_videos = driver.find_element(By.XPATH, "//div[@id='secondary-inner' and @class='style-scope "
                                                     "ytd-watch-flexy']")

    scroll_and_click(driver, sort_by_box)
    time.sleep(3)
    sort_by_new_option = driver.find_element(By.CSS_SELECTOR,
                                             "yt-sort-filter-sub-menu-renderer.ytd-comments-header-renderer > yt-dropdown-menu:nth-child(2) > tp-yt-paper-menu-button:nth-child(1) > tp-yt-iron-dropdown:nth-child(2) > div:nth-child(1) > div:nth-child(1) > tp-yt-paper-listbox:nth-child(1) > a:nth-child(2) > tp-yt-paper-item:nth-child(1)")
    scroll_and_click(driver, sort_by_new_option)
    time.sleep(3)
    driver.execute_script("arguments[0].remove();", suggested_videos)
    while True:

        def spinnerwait():
            while True:
                time.sleep(1)
                # spinners = driver.find_elements(By.XPATH, "//tp-yt-paper-spinner[@id='spinner']")
                spinners = driver.find_elements(By.XPATH, "//tp-yt-paper-spinner[@id='spinner']")
                visible_spinners = []

                for spinner in spinners:
                    try:
                        aria_hidden = spinner.get_attribute("aria-hidden")
                        aria_label = spinner.get_attribute("aria-label")
                    except StaleElementReferenceException:
                        continue

                    if aria_hidden == "true" or aria_label == "loading": continue

                    visible_spinners.append(spinner)

                # print(spinners[0].get_attribute('outerHTML'))
                print(f"waiting on spinners {len(spinners)}")
                if len(visible_spinners) == 0: break

        e_button_count = 1
        m_button_count = 1

        spinnerwait()

        def process_buttons(buttons: list):
            good_buttons = []
            for button in buttons:
                if not button.is_displayed(): continue
                good_buttons.append(button)
                # print(button.get_attribute('outerHTML'))
                scroll_and_click(driver=driver, el=button)
                driver.execute_script("arguments[0].remove();", button)
            return good_buttons

        # Loading comment replies loop
        while e_button_count > 0 or m_button_count > 0:
            expand_buttons = driver.find_elements(By.XPATH, "//ytd-button-renderer[@id='more-replies-sub-thread']")
            actual_expand_buttons = process_buttons(expand_buttons)

            # expand the comment replies button
            # ytd-button-renderer
            more_expand_buttons = driver.find_elements(By.CSS_SELECTOR,
                                                       "ytd-continuation-item-renderer.replies-continuation button[aria-label='Show more replies']")
            actual_more_expand_buttons = process_buttons(more_expand_buttons)

            e_button_count = len(actual_expand_buttons)
            m_button_count = len(actual_more_expand_buttons)

            if e_button_count != 0 or m_button_count != 0:
                spinnerwait()

        # Scroll down continuously
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight)")
        print("Scrolling down.")
        spinnerwait()

        # Check every 60 seconds if page height has increased
        if e_button_count == 0 and m_button_count == 0: print("No extra comment buttons found")
        if time.time() - last_check_time >= 15:
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            print(f"{new_height} != {prev_height} and {e_button_count} != 0 and {m_button_count}")
            if (new_height > prev_height) or (e_button_count != 0 and m_button_count != 0):
                prev_height = new_height  # Update stored height
            else:
                # print(f"{new_height} {prev_height}")
                break
            last_check_time = time.time()

    comments = driver.find_elements(By.XPATH,
                                    "//div[@id='body' and contains(@class, 'style-scope ytd-comment-view-model')]")
    print(f"Found {len(comments)} comments")
    comment_ids = set()
    for x in comments:
        result = parse_comment(x, videoID)
        if result: comment_ids.add(result)

    print(f"Better estimate of comments: {len(comment_ids)}")
    crsr.execute("UPDATE video SET scraped = 1 - scraped WHERE videoID = ?", (videoID,))
    conn.commit()


def video_transcript_parser(video_link):
    print(video_link)
    transcript = ytt_api.fetch(video_id=get_video_id(video_link=video_link))
    for x in transcript.snippets: print(x.text)


def parse_videos(driver, channelID: str = None, videoID: str = None, comments: bool = False):
    crsr.execute("SELECT DISTINCT channelID FROM channel WHERE channelID IS NOT NULL;")
    rows = crsr.fetchall()
    channel_ids = [row[0] for row in rows]

    crsr.execute("SELECT DISTINCT videoID FROM snippet WHERE videoID IS NOT NULL;")
    rows = crsr.fetchall()
    snippet_video_ids = [row[0] for row in rows]

    crsr.execute("SELECT DISTINCT videoID FROM comment WHERE videoID IS NOT NULL;")
    rows = crsr.fetchall()
    comment_video_ids = [row[0] for row in rows]

    if channelID:
        crsr.execute("SELECT * FROM video WHERE channelID = ?;", (channelID,))
        rows = crsr.fetchall()
        videos = rows
    elif videoID:
        crsr.execute("SELECT * FROM video WHERE videoID = ?;", (videoID,))
        rows = crsr.fetchall()
        videos = rows
    else:
        crsr.execute("SELECT * FROM video WHERE channelID IS NOT NULL;")
        rows = crsr.fetchall()
        videos = rows

    # unique_videoIDs = [video[0] for video in videos]

    for x in videos:
        if x[0] in comment_video_ids and comments: continue
        if x[0] in snippet_video_ids and not comments: continue
        if not x[4] and not comments: continue

        video_link = f"https://www.youtube.com/watch?v={x[0]}"
        video_parser(driver, video_link, x[1], comments)


class YoutubeLink:
    def __init__(self, link):
        self.text = link
        parsedURL = urlparse(link)
        host = (parsedURL.netloc or "").lower()
        path = parsedURL.path or ""
        qs = parse_qs(parsedURL.query)

        if host in "youtu.be":
            self.type = "video"
            return

        if host not in {"www.youtube.com", "youtube.com", "m.youtube.com"}:
            self.type = "unknown"
            return

        if path == "/playlist" and "list" in qs:
            self.type = "playlist"
            return

        if path == "/watch" and "v" in qs:
            self.type = "video"
            return

        if path == "/results" and "search_query" in qs:
            self.type = "search"
            return

        if path.startswith("/channel/") or path.startswith("/@"):
            self.type = "channel"
            return

        self.type = "unknown"


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main",
                                     description="A slow youtube scraper.")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    sub = parser.add_subparsers(required=True, dest="subcommand")

    auto = sub.add_parser(name="auto", help="Tries to auto-detect URL type and run the appropriate methods.")
    auto.add_argument("url", help="The Youtube URL.")

    comments = sub.add_parser(name="comments", help="Tries to scrape comments from a youtube video.")
    comments.add_argument("url", help="The Youtube video URL.")

    transcript = sub.add_parser(name="transcript", help="Tries to scrape the transcript from a youtube video.")
    transcript.add_argument("url", help="The Youtube video URL.")

    playlist = sub.add_parser(name="playlist", help="Tries to scrape youtube videos from a playlist.")
    playlist.add_argument("url", help="The Youtube playlist URL.")

    search = sub.add_parser(name="search", help="Tries to scrape a youtube search query results page.")
    search.add_argument("query", help="The Youtube search query URL.")
    search.add_argument("max-depth", default=100, type=int,
                        help="The maximum number of videos to scrape from the search results page.")

    channel = sub.add_parser(name="channel", help="Tries to scrape a channel's videos.")
    channel.add_argument("channel", help="The channel's URL.")

    return parser


def main(argsraw: list[str] | None = None) -> int:
    LOG = logging.getLogger(__name__)
    parser = build_argparser()
    args = parser.parse_args(args=argsraw)
    setup_logging(args.verbose)

    if args.headless: ff_options.add_argument('--headless')
    try:
        if args.subcommand == "auto":
            yt_link = YoutubeLink(link=args.url)
            if yt_link.type == "video":
                video_parser(driver=driver1, video_link=yt_link.text)
            elif yt_link.type == "search":
                query_parser(driver=driver1, query_link=yt_link.text, depth=100)
            elif yt_link.type == "channel":
                channel_parser(driver=driver1, channel_link=yt_link.text)
            elif yt_link.type == "playlist":
                if "&sp=" in yt_link.text:
                    print("Advanced queries are not implemented yet.")
                    return 2
                playlist_parser(driver=driver1, playlist_link=yt_link.text)
            else:
                print("Couldn't recognize the link.")
                return 2
        else:
            if args.subcommand == "comments":
                comment_parser(driver1, video_link=args.url)
            elif args.subcommand == "transcript":
                video_transcript_parser(video_link=args.url)
            elif args.subcommand == "playlist":
                if "&sp=" in args.url:
                    print("Advanced queries are not implemented yet.")
                    return 2
                playlist_parser(driver1, playlist_link=args.url)
            elif args.subcommand == "search":
                query_parser(driver1, query_link=args.url, depth=args.max_depth)
            elif args.subcommand == "channel":
                channel_parser(driver1, channel_link=args.url)
            else:
                print("Couldn't recognize the link.")
                return 2
        return 0
    except KeyboardInterrupt:
        LOG.warning("Interrupted.")
        return 130
    except Exception:
        LOG.exception("Failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

conn.close()
