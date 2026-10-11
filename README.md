# Super Scraper

**An asynchronous, customizable web scraper for collecting website content and building knowledge bases.**

Super Scraper is a Python-based web crawling and content extraction project built with `asyncio` and Playwright. It is designed to crawl websites, extract useful page content, and organize the results into a local corpus for research, documentation, and AI-assisted development.

The project aims to make web scraping more configurable, reliable, and accessible, with a beginner-friendly interface planned for easier setup and operation.

## Features

- **Asynchronous crawling:** Process multiple pages concurrently using Python's `asyncio`.
- **Browser-based scraping:** Use Playwright to access and extract content from supported websites.
- **Configurable concurrency:** Control the number of concurrent browser tasks.
- **Retry handling:** Retry failed requests with configurable delays.
- **Crawl state and resuming:** Preserve progress and resume interrupted scraping sessions.
- **Duplicate prevention:** Normalize canonical URLs to reduce duplicate pages.
- **Markdown support:** Attempt to retrieve Markdown versions of pages where available.
- **Content extraction:** Remove common navigation, scripts, footers, cookie notices, and other unwanted page elements.
- **Keyword-based collection:** Configure keywords to guide the crawling workflow.
- **Configurable output:** Choose the seed URLs and output location.
- **Error logging:** Record scraping errors for troubleshooting.
- **Robots.txt awareness:** Check applicable crawling rules before accessing pages.

## Use Cases

- Building documentation knowledge bases.
- Collecting publicly available technical documentation.
- Researching website content.
- Organizing resources for AI-assisted coding workflows.
- Exploring supported websites for development and testing.

## Requirements

- Python 3
- Playwright
- A supported browser installation
- Internet access for websites you are authorized to access

Install the project's dependencies using its dependency file if one is provided.

If Playwright is not installed, the usual setup is:

```bash
pip install playwright
playwright install
```

Check the repository's actual dependency list and Python version requirements before running the scraper.

## Configuration

The scraper is designed to support options such as:

| Option | Purpose |
|---|---|
| `--url` | Add a starting URL; can be supplied multiple times |
| `--keywords` | Configure keywords |
| `--output` | Choose the output file |
| `--max-pages` | Set the maximum page count |
| `--locale` | Set a documentation locale |
| `--all-locales` | Enable supported locale crawling |
| `--restart` | Restart a crawl |
| `--clear-state` | Clear saved crawl state |

Run the script's help command to confirm the available arguments and their exact syntax.

## Output

The default configuration uses files such as:

- `roblox_knowledge_base.txt` — collected content.
- `.errors.log` — scraping errors.
- `.state.json` — saved crawl state for resuming.

These filenames may vary depending on your configuration.

## Responsible Crawling

Only crawl websites you have permission to access and follow applicable laws, website terms, and access restrictions.

Super Scraper is designed to respect `robots.txt` crawling rules. Use reasonable concurrency and request delays, avoid overwhelming servers, and do not attempt to bypass authentication, paywalls, CAPTCHAs, or technical access controls.

## Roadmap

- [ ] Beginner-friendly desktop interface.
- [ ] Start, pause, resume, and stop controls.
- [ ] Live progress reporting and crawl statistics.
- [ ] Easy configuration for starting URLs, limits, and output formats.
- [ ] Export to formats such as JSON, CSV, and Markdown.
- [ ] Improved content filtering and extraction options.
- [ ] Clear error messages and recovery tools.
- [ ] Documentation, tests, and contributor guidelines.

Roadmap items represent planned work, not necessarily current functionality.

## Contributing

Contributions, bug reports, feature requests, and documentation improvements are welcome.

Before opening a pull request, explain the problem being solved, describe the changes, and include testing details where possible.

## License

A license has not been specified here. Add a `LICENSE` file before presenting the project as open source, and choose a license that matches your intentions.

---

**Built for developers who want to collect, organize, and work with web content more efficiently.**
