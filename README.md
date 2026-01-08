# selenium-youtube-scraper
A slow youtube scraper built with selenium and python. Stores channels, comments, and transcripts into a database file. Uses FireFox in order for the script to run with an adblocker.

### Usage
This project is currently using a CLI interface, so run the program from the command line, like so:
```
python main.py auto "https://www.youtube.com/watch?v=jNQXAC9IVRw"
```

#### CLI Commands
- auto: Tries to auto detect what kind of link you added, and works from there.
- comments: Takes in a video url and tries to save all the comments under it to the database.
- video: Takes in a video url and tries to save the generic content like its title and url.
- search: Takes in a youtube video search and tries to save the resulting videos to a certain depth.
- playlist: Takes in a playlist url and tries to save all videos on the playlist.
- --headless: Changes whether the script opens a visible window or not.
### Current Database Schema
<img width="719" height="756" alt="database schema" src="https://github.com/medt-ner/selenium-youtube-scraper/blob/main/dbSchema.png" />
