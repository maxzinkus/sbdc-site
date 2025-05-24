## Seattle Blues Dance Collective Website

Informational website for Blues social dancing events in Seattle, WA

[seattlebluesdance.com](https://seattlebluesdance.com)

### Running the site (local)

The site was built with [Python 3.13](https://www.python.org/downloads/release/python-3133/), and dependencies are managed with [`uv`](https://docs.astral.sh/uv/).

Once both `python3` and `uv` are installed:

```sh
$ uv venv .venv
$ source .venv/bin/activate
$ uv pip install -r pyproject.toml
```

Then to run the web app under Flask locally:
```sh
$ python app.py
```

And navigate to [http://localhost:5000](http://localhost:5000) in your browser.

### Licenses

- Logo image owned by [Lila Faria](https://www.lilaffaria.com), used with permission
- Instagram logo from [ClipArtCraft(CC)](https://clipartcraft.com)
- Instructor images owned by each respective instructor, used with permission

Max Zinkus, 2025 All Rights Reserved (for now)
