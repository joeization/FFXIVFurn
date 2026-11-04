# Data and distribution policy

[Back to README](../README.md)

## Distribution boundaries

This project separates code/documentation from local data. **Do not publish, provide downloads of, or package databases in releases, packages, or container layers.** This includes production databases, test databases, empty databases, backups, and SQLite WAL/SHM files. Classification, annotation, or format conversion does not establish redistribution rights.

Game/ReMakePlace meshes, textures, thumbnails, extracted packages, and their rights belong to their respective rights holders. This project's code grants no rights to use or distribute those materials. Model weights, classification runs, private layouts, generated images, and authentication settings are also excluded from source distributions. Users must check sources, licenses, and terms themselves. This document is repository maintenance policy, not a legal license or legal advice.

## Three safeguards

1. `.gitignore` ignores local directories and database/native-resource extensions anywhere. **It does not untrack existing files**, and `git add -f` bypasses it.
2. `.gitattributes` excludes those local directories/resources from `git archive`. This affects Git archives only, not manual ZIPs, Docker build contexts, wheels, or web attachments.
3. `python scripts/check_distribution.py` checks currently indexed paths and fails on restricted paths/extensions. `--directory PATH` additionally checks an extracted source archive or prepared distribution directory without modifying files.

## Before publishing

- Run the checker and tests. For new files not yet indexed, also check the prepared distribution directory.
- Create a **source-only** archive from a clean source tree or Git archive, not the entire working directory. There is currently no official automatic release or Python packaging setup.
- Extract the archive and run `python scripts/check_distribution.py --directory <extracted-path>`. Manually inspect images, JSON, CSVs, and other unlisted extensions for private/third-party content.
- Do not upload databases, extracted game assets, model weights, or the entire `data/` directory. Any future package/Docker/CI release workflow needs a separate allowlist; no such workflow was created during this cleanup.
- Check historical commits, tags, remote releases, and attachments. The source-tree/archive checks do not establish that old history or remote attachments have been cleaned.

If files are already tracked, ignore rules alone are insufficient. Separately assess index removal and history/remote handling. Distribution checks do not delete local data, rewrite history, commit, push, or publish releases.

## Code license

Code and original project documentation use the [MIT License](../LICENSE). Preserve its copyright and license notices when using or distributing it.

MIT does not cover local databases, game/ReMakePlace meshes, textures, thumbnails, packages, model weights, or other third-party content. This project grants no distribution rights to them. The policy prohibiting databases/assets in this project's releases, attachments, and packages remains unchanged. Dependencies and referenced materials retain their own licenses.
