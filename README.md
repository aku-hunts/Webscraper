# Super Scraper

**An asynchronous Python web scraper for collecting documentation and building AI-ready knowledge bases.**

Super Scraper uses Python, `asyncio`, and Playwright to crawl documentation websites, extract useful content, and save it into a consolidated text file. It prioritizes clean Markdown when available and falls back to browser-based extraction when necessary.

The project currently targets Roblox Creator Documentation and Luau documentation, with configurable crawling behavior defined in the Python source code.

## Features

- **Asynchronous crawling** — Processes multiple pages concurrently.
- **Playwright integration** — Extracts content from browser-rendered pages.
- **Markdown-first extraction** — Attempts to retrieve clean Markdown before using browser rendering.
- **Content cleaning** — Removes common navigation elements, scripts, cookie notices, and other page clutter.
- **Robots.txt awareness** — Checks crawling rules before accessing pages.
- **Retry handling** — Retries failed operations with configurable delays.
- **Duplicate prevention** — Tracks visited pages and normalizes URLs.
- **Concurrency controls** — Limits simultaneous browser workers.
- **Error logging** — Records failed URLs and exception details.
- **Knowledge base output** — Combines collected content into a single text file suitable for research and AI-assisted development.

## Current scope

The default configuration targets:

- [Roblox Creator Documentation](https://create.roblox.com/docs)
- [Luau Documentation](https://luau-lang.org/)

The crawler uses an allowlist of domains and permitted URL paths. Other websites are not automatically supported simply by changing the starting URL; the relevant configuration and URL filtering logic may also need to be updated.

## Requirements

- Python 3.10 or newer recommended.
- pip
- Playwright
- Chromium installed through Playwright
- An internet connection

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/aku-hunts/Webscraper.git
cd Webscraper
```

### 2. Create a virtual environment

**Windows PowerShell:**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can run the commands below using the virtual environment's Python executable directly.

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Install the browser

```bash
python -m playwright install chromium
```

## Usage

Start the scraper with:

```bash
python super_scraper.py
```

The current version reads its default URLs and crawl settings from the configuration section near the beginning of `super_scraper.py`.

You can adjust settings such as:

- Starting URLs
- Allowed domains and paths
- Maximum pages per crawl
- Number of concurrent workers
- Request delays
- Navigation timeout
- Retry attempts and retry delays
- Output and error-log filenames

These settings currently require editing the source code. A beginner-friendly graphical interface and command-line configuration are planned improvements, not existing features.

## Output files

By default, the scraper generates:

| File | Purpose |
|---|---|
| `roblox_knowledge_base.txt` | Consolidated extracted content |
| `scraping_errors.log` | Errors and exception details from failed operations |

Generated files are local outputs and should generally not be committed to the repository.

## Responsible crawling

Use Super Scraper only on websites you are authorized to access.

- Review the target website's terms and applicable laws.
- Respect `robots.txt` rules and access restrictions.
- Use reasonable request delays and concurrency.
- Do not attempt to bypass authentication, paywalls, CAPTCHAs, or other access controls.
- Review a website's policies before adapting the crawler to a new domain.

Robots.txt is a crawler guidance mechanism, not a substitute for permission or legal review.

## Roadmap

Planned improvements include:

- [ ] Beginner-friendly graphical interface
- [ ] Start, pause, resume, and stop controls
- [ ] Configurable starting URLs without editing source code
- [ ] Live progress tracking and crawl statistics
- [ ] Additional export formats, including JSON and Markdown
- [ ] Improved site configuration and content filtering
- [ ] Better recovery and error reporting
- [ ] Automated tests and continuous integration
- [ ] More comprehensive installation and usage documentation

Roadmap items are planned features and may change as development progresses.

## Contributing

Contributions, bug reports, and suggestions are welcome.

When submitting changes, describe the problem, explain the proposed solution, and include testing details where possible.

## License

Super Scraper is released under the MIT License. See [LICENSE](LICENSE) for details.

---

**Built by [Akurocks](https://github.com/aku-hunts).**
