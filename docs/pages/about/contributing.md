# Contributing

Contributions are welcome: bug reports, ideas, documentation fixes and code. The full guide is [CONTRIBUTING.md](https://github.com/KIT-IWU-HydroEng/capiQ/blob/main/CONTRIBUTING.md) on GitHub: development setup, checks and tests, dependencies, and the commit and pull request conventions.

- **Report a bug or suggest an improvement**: open an [issue](https://github.com/KIT-IWU-HydroEng/capiQ/issues). Attach the capiQ log file if it helps.
- **Improve this documentation**: every page has an edit button that opens its source on GitHub.

## Working on the documentation

The pages are Markdown files in `docs/pages/`, built with [Zensical](https://zensical.org); the site configuration, including the navigation, is `docs/zensical.toml`. Zensical is part of the development tools installed by `uv sync`.

From the project root:

```bash
uv run zensical serve -f docs/zensical.toml
```

opens a live preview at <http://localhost:8000> that reloads when a page is saved. To build the site as CI does (warnings, e.g. broken links or a missing example file, stop the build):

```bash
uv run zensical build -f docs/zensical.toml --clean --strict
```

The result is written to `docs/site/` (not committed). To show a repository file on a page, include it instead of copying its content, so the page follows the file:

````markdown
```json
--8<-- "example_files/input/results.json"
```
````

After a pull request is merged into `main`, GitHub Actions publishes the site to <https://kit-iwu-hydroeng.github.io/capiQ/>.
